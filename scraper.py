#! /usr/bin/env python3
#
# Copyright (c) 2018-2020 FASTEN.
#
# This file is part of FASTEN
# (see https://www.fasten-project.eu/).
#
# Licensed to the Apache Software Foundation (ASF) under one
# or more contributor license agreements.  See the NOTICE file
# distributed with this work for additional information
# regarding copyright ownership.  The ASF licenses this file
# to you under the Apache License, Version 2.0 (the
# "License"); you may not use this file except in compliance
# with the License.  You may obtain a copy of the License at
#
#   http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing,
# software distributed under the License is distributed on an
# "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY
# KIND, either express or implied.  See the License for the
# specific language governing permissions and limitations
# under the License.
#

import datetime
import json
import argparse
import time
import psycopg2
from abc import ABC, abstractmethod
from psycopg2 import OperationalError
from kafka import KafkaProducer

# Some statically defined variables.
host = "udd-mirror.debian.net"
user = "udd-mirror"
password = "udd-mirror"
date_format = "%Y-%m-%d %H:%M:%S"


class DebianPackageRelease:
    """Represents a Debian Package Release.
    """

    def __init__(self, package, version, source, source_version, date, arch,
                 release):
        self.package = package
        self.source = source
        self.version = version
        self.source_version = source_version
        self.date = date
        self.arch = arch  # Architecture (amd64, powerpc, all, etc.)
        self.release = release  # Debian Release (buster, sid, etc.)

    def print_release(self):
        """Prints a Debian package release.
        """
        print("Release: {0}-{1}-{2}-{3}. Uploaded at: {4}".format(
            self.package,
            self.version,
            self.arch,
            self.release,
            str(self.date)
        ))

    def to_json(self):
        """Dumps a Debian Package Release into JSON format.
        """
        return json.dumps({
            "package": self.package,
            "version": self.version,
            "arch": self.arch,
            "release": self.release,
            "source": self.source,
            "source_version": self.source_version,
            "date": str(self.date)
        })


class Udd(ABC):
    """Get Debian Packages Releases using UDD mirror"""

    host = host
    user = user
    password = password
    dbname = 'udd'

    def __init__(self, bootstrap_servers=None, kafka_topic=None,
                 is_c=False, release=None, arch=None):
        self.servers = bootstrap_servers
        self.topic = kafka_topic
        self.is_c = is_c
        self.release = release
        self.arch = arch
        self.con = None
        self.produce = self.to_print

        if self.servers is not None and self.topic is not None:
            self.produce = self.to_kafka


        try:
            self.con = self._connect_db()
        except OperationalError:
            print("Cannot connect to database {}:{}".format(host, 'udd'))

    def _connect_db(self):
        """Return a connection to database.

            Raises: OperationalError
        """
        try:
            con = psycopg2.connect(
                host=self.host, user=self.user,
                password=self.password, dbname=self.dbname
            )
        except OperationalError:
            raise
        return con

    @abstractmethod
    def query(self):
        """Query db for releases.
        """

    def parse_query(self, query_result):
        """Parses a query and returns Debian Packages Releases.
        """
        releases = []

        for row in query_result:
            releases.append(
                DebianPackageRelease(
                    row[0], row[1], row[2], row[3], row[4], row[5], row[6]
                )
            )
        return releases

    def get_releases(self):
        """Get Debian Packages Releases.
        """
        releases = []

        if self.con is None:
            return releases

        releases = self.parse_query(self.query())
        print(len(releases))

        # Return them sorted.
        return sorted(releases, key=lambda x: x.date)

    def to_print(self):
        """Print Debian Packages Releases to stdout/
        """
        releases = self.get_releases()

        for release in list(releases):
            print(release.to_json())

        # Return latest date (if any new releases are found).
        if len(releases) == 0:
            if hasattr(self, 'start_date'):
                return self.start_date
            else:
                return str(datetime.datetime.today().strftime(date_format))
        return releases[-1].date.replace(tzinfo=None)


    def to_kafka(self):
        """Get all Debian Packages Releases from a certain date
        and push to Kafka.
        """
        releases = self.get_releases()

        producer = KafkaProducer(
            bootstrap_servers=self.servers.split(','),
            value_serializer=lambda x: x.encode('utf-8')
        )

        for release in releases:
            release.print_release()
            producer.send(self.topic, release.to_json())

        producer.flush()
        print("{0}: Sent {1} releases.".format(
            str(datetime.datetime.now()), len(releases))
        )

        # Return latest date (if any new releases are found).
        if len(releases) == 0:
            if hasattr(self, 'start_date'):
                return self.start_date
            else:
                return str(datetime.datetime.today().strftime(date_format))
        return releases[-1].date.replace(tzinfo=None)


class AllUdd(Udd):
    """Fetch the latest releases of all packages.
    """

    def query(self):
        cursor = self.con.cursor()

        check_is_c = (" tag LIKE '%implemented-in::c%' "
                      if self.is_c else '')
        check_release = (" release = '{}' ".format(self.release)
                         if self.release else '')
        check_arch = (" architecture = '{}' ".format(self.arch)
                      if self.arch else '')

        checks = [check_is_c, check_release, check_arch]
        check = ''
        for counter, i in enumerate(checks):
            check += i
            if counter < len(checks)-1:
                if checks[counter+1] != '':
                    check += "AND"

        check = "WHERE " + check if check != '' else ''

        query = ("SELECT package, packages.version, packages.source, "
                 "source_version, date, architecture, release "
                 "FROM packages INNER JOIN upload_history ON "
                 "upload_history.source = packages.source AND "
                 "upload_history.version = packages.source_version "
                 "{}"
                ).format(check)

        cursor.execute(query)
        return cursor.fetchall()


class PackageUdd(Udd):
    """Fetch release(s) of a single package.
    """

    def __init__(self, bootstrap_servers=None, kafka_topic=None,
                 is_c=False, release=None, arch=None, package='',
                 version=None):
        super(PackageUdd, self).__init__(
            bootstrap_servers, kafka_topic, is_c, release, arch
        )
        self.package = package
        self.version = version

    def query(self):
        cursor = self.con.cursor()

        check_is_c = (" AND tag LIKE '%implemented-in::c%' "
                      if self.is_c else '')
        check_release = (" AND release = '{}' ".format(self.release)
                         if self.release else '')
        check_arch = (" AND architecture = '{}' ".format(self.arch)
                      if self.arch else '')
        check_version = (" AND version = '{}' ".format(self.version)
                         if self.version else '')

        check = "{}{}{}{}".format(
            check_is_c, check_release, check_arch, check_version
        )

        query = ("SELECT package, packages.version, packages.source, "
                 "source_version, date, architecture, release "
                 "FROM packages INNER JOIN upload_history ON "
                 "upload_history.source = packages.source AND "
                 "upload_history.version = packages.source_version "
                 "WHERE package = '{}' "
                 "{}"
                ).format(self.package, check)

        cursor.execute(query)
        return cursor.fetchall()


class DateUdd(Udd):
    """Fetch releases from a starting date.
    """

    def __init__(self, bootstrap_servers=None, kafka_topic=None,
                 is_c=False, release=None, arch=None, package=None,
                 date=''):
        super(DateUdd, self).__init__(
            bootstrap_servers, kafka_topic, is_c, release, arch
        )
        self.package = package
        self.start_date = date

    def query(self):
        cursor = self.con.cursor()

        check_is_c = (" AND tag LIKE '%implemented-in::c%' "
                      if self.is_c else '')
        check_release = (" AND release = '{}' ".format(self.release)
                         if self.release else '')
        check_arch = (" AND architecture = '{}' ".format(self.arch)
                      if self.arch else '')
        check_package = (" AND package = '{}' ".format(self.package)
                         if self.package else '')

        check = "{}{}{}{}".format(
            check_is_c, check_release, check_arch, check_package
        )

        query = ("SELECT package, packages.version, packages.source, "
                 "source_version, date, architecture, release "
                 "FROM packages INNER JOIN upload_history ON "
                 "upload_history.source = packages.source AND "
                 "upload_history.version = packages.source_version "
                 "WHERE date > '{start_date}+00' "
                 "{check}").format(
                     start_date=self.start_date,
                     check=check
                 )

        cursor.execute(query)
        return cursor.fetchall()


def get_parser():
    parser = argparse.ArgumentParser(
        "Scrape Debian packages releases, and optionally push them to Kafka."
    )
    parser.add_argument(
        '-a',
        '--architecture',
        type=str,
        default=None,
        help='Specify an architecture (e.g. amd64).'
    )
    parser.add_argument(
        '-b',
        '--bootstrap-servers',
        type=str,
        default=None,
        help="Kafka servers, comma separated."
    )
    parser.add_argument(
        '-C',
        '--not-only-c',
        action='store_true',
        help='Fetch all types of packages releases (not only C packages).'
    )
    parser.add_argument(
        '-d',
        '--start-date',
        type=lambda s: datetime.datetime.strptime(s, date_format),
        help=("The date to start scraping from. Must be in "
              "%%Y-%%m-%%d %%H:%%M:%%S format.")
    )
    parser.add_argument(
        '-f',
        '--forever',
        action='store_true',
        help="Run forever. Always use it with --start-date."
    )
    parser.add_argument(
        '-p',
        '--package',
        type=str,
        help='Package name to fetch.'
    )
    parser.add_argument(
        '-r',
        '--release',
        type=str,
        default=None,
        help='Specify Debian Release (e.g. buster).'
    )
    parser.add_argument(
        '-s',
        '--sleep-time',
        type=int,
        default=43200,
        help=("Time to sleep in between each scrape (in sec). Use it with "
              "--start-date option. Default 43.200 seconds (12 hours).")
    )
    parser.add_argument(
        '-t',
        '--topic',
        type=str,
        default=None,
        help="Kafka topic to push to."
    )
    parser.add_argument(
        '-v',
        '--version',
        type=str,
        help='Version of a specific version. Always use it with --package.'
    )
    return parser


def main():
    parser = get_parser()
    args = parser.parse_args()

    # Check arguments
    if args.version and not args.package:
        parser.error("--version must be used with --package")
    if args.forever and not args.start_date:
        parser.error("--forever must be used with --start-date")
    if args.topic and not args.bootstrap_servers:
        parser.error("--topic must be used with --bootstrap-servers")
    if args.bootstrap_servers and not args.topic:
        parser.error("--bootstrap-servers must be used with --topic")
    # Retrieve all arguments.
    arch = args.architecture
    bootstrap_servers = args.bootstrap_servers
    debian_release = args.release
    forever = args.forever
    is_c = False if args.not_only_c else True
    kafka_topic = args.topic
    latest_date = args.start_date
    package = args.package
    sleep_time = args.sleep_time
    version = args.version

    if latest_date:
        udd_con = DateUdd(
            bootstrap_servers, kafka_topic,
            is_c, debian_release, arch, package, latest_date
        )
    elif package:
        udd_con = PackageUdd(
            bootstrap_servers, kafka_topic,
            is_c, debian_release, arch, package, version
        )
    else:
        udd_con = AllUdd(
            bootstrap_servers, kafka_topic,
            is_c, debian_release, arch
        )

    # Forever: get releases from start_date, update latest_date based on
    # latest release and push this to Kafka.
    if forever:
        while True:
            print("{0}: Scraping releases from {1} to now.".format(
                str(datetime.datetime.now()),
                str(latest_date)
            ))
            latest_date = udd_con.produce()
            time.sleep(sleep_time)
    else:
        udd_con.produce()


if __name__ == "__main__":
    main()
