#! /usr/bin/env python3
import argparse
import time
import gzip
import re
import json
import os
import sys
import ast
import datetime

from io import BytesIO
from collections import defaultdict

import pycurl

from fasten.plugins.kafka import KafkaPlugin
from fasten.plugins.base import PluginError


PKGS_FILE = "pkgs.json"
LAST_REQUEST = None
# https://wiki.debian.org/DebianBuster
BUSTER_TIMESTAMPS = [
    "20190707T211830Z", # 10.0
    "20190908T222211Z", # 10.1
    "20191117T204416Z", # 10.2
    "20200209T205554Z", # 10.3
    "20200510T203930Z", # 10.4
    "20200802T204950Z", # 10.5
    "20200927T204254Z", # 10.6
    "20201206T204150Z", # 10.7
    "20210207T205150Z", # 10.8
    "20210328T030002Z", # 10.9
]


DEB_LOOKUP = [
    '0', '2', '3', '4', '6', '7', '9', 'a', 'b', 'c', 'd', 'e', 'f', 'g', 'h',
    'i', 'j', 'k', 'm', 'n', 'o', 'p', 'q', 'r', 's', 't', 'u', 'v', 'w', 'x',
    'y', 'z'
]
# Only packages from l can be in different directories
DEB_LOOKUP_L = [
    'lib3', 'liba', 'libb', 'libc', 'libd', 'libe', 'libf',
    'libg', 'libh', 'libi', 'libj', 'libk', 'libl', 'libm', 'libn', 'libo',
    'libp', 'libq', 'libr', 'libs', 'libt', 'libu', 'libv', 'libw', 'libx',
    'liby', 'libz'
]

def find_deb_prefix(name):
    if name[0] != 'l' and name[0] in DEB_LOOKUP:
        return name[0]
    if name[0] == 'l':
        if len(name) >= 4:
            if name[:4] in DEB_LOOKUP_L:
                return name[:4]
        return 'l'
    return False


class MyHTTPException(Exception):
    pass


class MyHTTP404Exception(Exception):
    pass


class MyHTTPTimeoutException(Exception):
    pass


def download(url):
    """Download from snapshot.d.o. This function was imported from
    https://salsa.debian.org/josch/metasnap/-/blob/master/run.py
    with few changes.
    """
    f = BytesIO()
    maxretries = 10
    for retrynum in range(maxretries):
        try:
            c = pycurl.Curl()
            c.setopt(
                c.URL,
                url,
            )
            # even 100 kB/s is too much sometimes
            c.setopt(c.MAX_RECV_SPEED_LARGE, 1000 * 1024)  # bytes per second
            c.setopt(c.CONNECTTIMEOUT, 30)  # the default is 300
            # sometimes, curl stalls forever and even ctrl+c doesn't work
            start = time.time()

            def progress(*data):
                # a download must not last more than 10 minutes
                # with 100 kB/s this means files cannot be larger than 62MB
                if time.time() - start > 10 * 60:
                    print("transfer took too long")
                    # the code will not see this exception but instead get a
                    # pycurl.error
                    raise MyHTTPTimeoutException(url)

            c.setopt(pycurl.NOPROGRESS, 0)
            c.setopt(pycurl.XFERINFOFUNCTION, progress)
            # $ host snapshot.debian.org
            # snapshot.debian.org has address 185.17.185.185
            # snapshot.debian.org has address 193.62.202.27
            # c.setopt(c.RESOLVE, ["snapshot.debian.org:80:185.17.185.185"])
            if f.tell() != 0:
                c.setopt(pycurl.RESUME_FROM, f.tell())
            c.setopt(c.WRITEDATA, f)
            c.perform()
            if c.getinfo(c.RESPONSE_CODE) == 404:
                raise MyHTTP404Exception("got HTTP 404 for %s" % url)
            elif c.getinfo(c.RESPONSE_CODE) not in [200, 206]:
                raise MyHTTPException(
                    "got HTTP %d for %s" % (c.getinfo(c.RESPONSE_CODE), url)
                )
            c.close()
            # if the requests finished too quickly, sleep the remaining time
            # s/r  r/h
            # 3    1020
            # 2.5  1384
            # 2.4  1408
            # 2    1466
            # 1.5  2267
            seconds_per_request = 1.5
            global LAST_REQUEST
            if LAST_REQUEST is not None:
                sleep_time = seconds_per_request - (time.time() - LAST_REQUEST)
                if sleep_time > 0:
                    time.sleep(sleep_time)
            LAST_REQUEST = time.time()
            return f.getvalue()
        except pycurl.error as e:
            code, message = e.args
            if code in [
                pycurl.E_PARTIAL_FILE,
                pycurl.E_COULDNT_CONNECT,
                pycurl.E_ABORTED_BY_CALLBACK,
            ]:
                if retrynum == maxretries - 1:
                    break
                sleep_time = 4 ** (retrynum + 1)
                print("retrying after %f s..." % sleep_time)
                time.sleep(sleep_time)
                continue
            else:
                raise
        except MyHTTPException as e:
            print("got HTTP error:", repr(e))
            if retrynum == maxretries - 1:
                break
            sleep_time = 4 ** (retrynum + 1)
            print("retrying after %f s..." % sleep_time)
            time.sleep(sleep_time)
            # restart from the beginning or otherwise, the result might
            # include a varnish cache error message
            f = BytesIO()
    raise Exception("failed too often...")


def decompress(data):
    """Decompress data downloaded from a .gz file.
    """
    bytes_data = gzip.decompress(data)
    string_data = bytes_data.decode("utf-8")
    return string_data


def find_packages(string_data):
    """Find packages (dsc) from a file with multiple Debian source control
    files.
    """
    return re.findall(r'(?s)(Package: .*?)(?:(?:\r*\n){2})', string_data)


def get_package(string_data):
    """Get the dsc from a file that contain a dsc or a pgp signature and dsc.
    """
    if string_data.startswith("--"): # Signature
        try:
            m = re.findall(r'(?s)(\n\n.*: .*?)(?:(?:\r*\n){2})', string_data)
            return m[0].strip()
        except:
            return string_data
    else:
        return string_data


# https://www.debian.org/doc/debian-policy/ch-controlfields.html
# #s-debiansourcecontrolfiles
def parse_package(string_package):
    """Parse a Debian source control file (from string) to a dict where each
    file is a key. We add one more key `dsc` which contains the string we
    processed.
    """
    res = {'dsc': string_package}
    current_field = None
    for line in string_package.splitlines():
        if not line.startswith(' '):
            field, contents = line.split(":", 1)
            current_field = field
            contents = contents.strip()
            if field in ["Package", "Source"]:
                res["Source"] = contents
            # Single line string
            elif field in ["Format", "Version", "Maintainer",
                         "Homepage", "Vcs-Browser", "Testsuite",
                         "Standards-Version", "Section", "Priority",
                         "Directory"]:
                res[field] = contents
            elif field in ["Vcs-Arch", "Vcs-Bzr", "Vcs-Cvs", "Vcs-Darcs",
                           "Vcs-Git", "Vcs-Hg", "Vcs-Mtn", "Vcs-Svn"]:
                res[field] = contents
                res["Vcs"] = contents
            # Single line comma separated
            elif field in ["Binary", "Uploaders", "Testsuite-Triggers",
                           "Build-Depends", "Build-Depends-Indep",
                           "Build-Depends-Arch", "Build-Conflicts",
                           "Build-Conflicts-Indep", "Build-Conflicts-Arch"]:
                res[field] = list(map(lambda x: x.strip(),
                                      contents.split(",")))
            # Single line space separated
            elif field in ["Architecture"]:
                res[field] = list(map(lambda x: x.strip(),
                                      contents.split(" ")))
            elif field in ["Dgit"]:
                res[field] = contents.split(" ")[0]
            elif field in ["Package-List", "Checksums-Sha1",
                           "Checksums-Sha256", "Files"]:
                res[field] = []
        else:
            contents = line.strip()
            if current_field == "Package-List":
                contents = contents.split(" ")
                contents = {
                    "name": contents[0],
                    "type": contents[1],
                    "section": contents[2],
                    "priority": contents[3],
                    "arch": [] if len(contents) < 5 else
                    contents[4].split("=")[1].split(",")}
                res[current_field].append(contents)
            elif current_field in ["Files", "Checksums-Sha1",
                                   "Checksums-Sha256"]:
                contents = contents.split(" ")
                contents = {
                    "checksum": contents[0],
                    "size": contents[1],
                    "filename": contents[2]}
                res[current_field].append(contents)
    return res


def save(data, filename):
    with open(filename, "w") as out:
        out.write(data)


def parse_packages(data, whitelist):
    """Filter out packages that are not in whitelist.
    """
    if whitelist is not None:
        return list(filter(lambda x: x['Source'] in whitelist,
                           [parse_package(p) for p in data]))
    return [parse_package(p) for p in data]


def add_pkg_to_pkgs(pkg, pkgs):
    """Add package to dictionary of packages.
    """
    name = pkg["Source"]
    version = pkg["Version"]
    pkgs[name][version] = pkg
    return pkgs


def add_pkgs_to_pkgs(data, pkgs):
    new_pkgs_counter = 0
    new_revisions = list()
    for pkg in data:
        name = pkg["Source"]
        version = pkg["Version"]
        if name not in pkgs:
            new_pkgs_counter += 1
        if version not in pkgs[name]:
            new_revisions.append(pkg)
        pkgs[name][version] = pkg
    return new_pkgs_counter, new_revisions, pkgs


def process_sources_gz(archive, timestamp, dist, section,
                       pkgs, whitelist, releases_dir):
    url = "https://snapshot.debian.org/archive/{}/{}/dists/{}/{}/{}".format(
        archive,
        timestamp,
        dist,
        section,
        "source/Sources.gz"
    )
    data = download(url)
    data = decompress(data)
    if releases_dir:
        dest_filename = os.path.join(releases_dir, timestamp + ".dsc")
        os.makedirs(releases_dir, exist_ok=True)
        save(data, dest_filename)
    data = find_packages(data)
    data = parse_packages(data, whitelist)
    new_pkgs_counter, new_revisions, pkgs = add_pkgs_to_pkgs(data, pkgs)
    return pkgs, new_pkgs_counter, new_revisions


def process_dsc(url, pkgs, whitelist):
    data = download(url)
    data = data.decode("utf-8")
    package = get_package(data)
    pkg = parse_package(package)
    pkgs = add_pkg_to_pkgs(pkg, pkgs)
    return pkgs


class DSCAnalyzerKafkaPlugin(KafkaPlugin):
    def __init__(self, bootstrap_servers, consume_topic, produce_topic,
                 log_topic, error_topic, group_id, directory, debug, pkgs,
                 whitelist, releases_dir):
        super().__init__(bootstrap_servers)
        self.consume_topic = consume_topic
        self.produce_topic = produce_topic
        self.log_topic = log_topic
        self.error_topic = error_topic
        self.group_id = group_id
        self.directory = directory
        self.releases_dir = releases_dir
        self.debug = debug
        self.pkgs = pkgs
        self.whitelist = whitelist
        self.record = None
        if not debug:
            self.set_consumer()
            self.set_producer()
        if debug:
            self.consume_topic = "consume_topic"
            self.produce_topic = "produce_topic"
            self.log_topic = "log_topic"
            self.error_topic = "error_topic"
            os.makedirs("debug", exist_ok=True)

    def name(self):
        return "DSCAnalyzerKafkaPlugin"

    def description(self):
        return "A Kafka plug-in that downloads and analyzes dsc files"

    def version(self):
        return "0.0.1"

    def free_resource(self):
        pass

    def _parse_record(self):
        try:
            timestamp = self.record['timestamp']
            archive = self.record['archive']
            distribution = self.record['distribution']
            component = self.record['component']
            return timestamp, archive, distribution, component
        except KeyError:
            message = self.create_message(
                self.record, {"message": "Malformed record"})
            self.emit_message(self.log_topic, message, "failed", "")
            self.emit_message(self.error_topic, message, "error", "")

    def _process(self, timestamp, archive, distribution, component):
        try:
            pkgs, new_pkgs_counter, new_revisions = process_sources_gz(
                archive, timestamp, distribution,
                component, self.pkgs, self.whitelist, self.releases_dir
            )
            return pkgs, new_pkgs_counter, new_revisions
        except:
            message = self.create_message(
                self.record, {"message": "Downloading failed"})
            self.emit_message(self.log_topic, message, "failed", "")
            self.emit_message(self.error_topic, message, "error", "")

    def _produce_messages(self, new_revisions):
        for pkg in new_revisions:
            pkg.pop('dsc', None)
            payload = {
                "source": pkg['Source'],
                "version": pkg['Version'],
                "release": self.record['distribution'],
                # TODO currently we support only amd64
                # We should generate a message per supported architecture.
                "arch": "amd64",
                "forge": "debian",
                "dsc": pkg
            }
            message = self.create_message(
                self.record, {"payload": payload})
            self.emit_message(self.produce_topic, message, "succeed", "")

    def consume(self, record):
        """First download the sources, then run sbuild, and finally check the
           results.
        """
        self.record = record
        res = self._parse_record()
        if not res:
            self.record = None
            return
        timestamp, archive, distribution, component = res

        # Begin
        message = self.create_message(self.record, {"status": "begin"})
        self.emit_message(self.log_topic, message, "begin", "")

        res = self._process(timestamp, archive, distribution, component)
        if not res:
            self.record = None
            return
        pkgs, new_pkgs_counter, new_revisions = res

        # Save to disk
        save_to_directory(new_revisions, self.directory)
        save_packages(self.directory, pkgs)

        # Produce messages
        self._produce_messages(new_revisions)

        # Logging
        message = self.create_message(
            record, {"stats": {"new packages": new_pkgs_counter,
                     "new revisions": len(new_revisions)}})
        self.emit_message(self.log_topic, message, "stats", "")
        message = self.create_message(record, {"status": "success"})
        self.emit_message(self.log_topic, message, "complete", "")

        self.record = None

    def emit_message(self, topic, msg, phase, log_msg):
        if self.debug:
            self.log("{}: Phase: {} Sent: {} to {}".format(
                str(datetime.datetime.now()), phase, log_msg, topic
            ))
            filename = "/root/debug/" + topic + ".json"
            json.dump(msg, open(filename, 'a'))
            with open(filename, 'a') as f:
                f.write("\n")
        else:
            super().emit_message(topic, msg, phase, log_msg)


def get_args():
    parser = argparse.ArgumentParser(
        "DSC Analyzer",
        description=("Download and analyze Debian Source Control Files from "
                     "snapshot.d.o.")
    )
    parser.add_argument(
        '-d',
        '--directory',
        type=str,
        help="Path to base directory where dsc files, and state will be saved."
    )
    parser.add_argument(
        '--releases-dir',
        type=str,
        help="Path to directory where dsc files for releases will be saved."
    )
    parser.add_argument(
        '-w',
        '--whitelist',
        type=str,
        help="File with Debian package names to process"
    )
    parser.add_argument(
        '-D',
        '--debug',
        type=str,
        help="Debug mode for testing Kafka implementation."
    )
    parser.add_argument(
        '-A',
        '--all',
        action='store_true',
        default=False,
        help="Do not use a whitelist"
    )
    parser.add_argument(
        '-t',
        '--timestamps',
        nargs='+',
        default=BUSTER_TIMESTAMPS,
        help=(
            "A list of timestamps (default: timestamps for releases of Debian "
            "buster."
        )
    )
    parser.add_argument(
        '--distribution',
        type=str,
        default="buster",
        help="Debian distribution (Default: buster)"
    )
    parser.add_argument(
        '-a',
        '--archive',
        type=str,
        default="debian",
        help="Debian archive (Default: debian)"
    )
    parser.add_argument(
        '-c',
        '--component',
        type=str,
        default="main",
        help="Debian component (Default: main)"
    )
    parser.add_argument(
        '-s',
        '--single-package',
        type=str,
        help="Parse a single package (You must provide a url with --url option)"
    )
    parser.add_argument(
        '-u',
        '--url',
        type=str,
        help=("Provide a URL for downloading a single file. It will ignore "
              "the options --archive, --component, --distribution, "
              "--timestamps."
        )
    )
    # Kafka related options
    parser.add_argument(
        '-i',
        '--in-topic',
        type=str,
        help="Kafka topic to read from."
    )
    parser.add_argument(
        '-o',
        '--out-topic',
        type=str,
        help="Kafka topic to write to."
    )
    parser.add_argument(
        '-e',
        '--err-topic',
        type=str,
        help="Kafka topic to write errors to."
    )
    parser.add_argument(
        '-l',
        '--log-topic',
        type=str,
        help="Kafka topic to write logs to."
    )
    parser.add_argument(
        '-b',
        '--bootstrap-servers',
        type=str,
        help="Kafka servers, comma separated."
    )
    parser.add_argument(
        '-g',
        '--group',
        type=str,
        help="Kafka consumer group to which the consumer belongs."
    )
    parser.add_argument(
        '--sleep-time',
        type=int,
        default=21600,
        help="Time to sleep in between each consuming (in sec) -- only with -i."
    )
    args = parser.parse_args()
    kafka_args = (args.out_topic, args.err_topic,
                  args.log_topic, args.bootstrap_servers, args.group)

    # Handle options
    if (args.debug and any(x for x in kafka_args)):
        message = "You cannot use any kafka option with --debug option."
        raise parser.error(message)
    if (any(x for x in kafka_args) and not all(x for x in kafka_args)):
        message = "You should always use -i, -o, -e, -l, -b, and -g together."
        raise parser.error(message)
    if (args.single_package or args.url):
        message = "We don't support --single-package and --url yet"
        raise parser.error(message)
    return args


def load_packages(directory):
    res = defaultdict(lambda: {})
    pkgs_file = os.path.join(directory, PKGS_FILE) if directory else PKGS_FILE
    if os.path.exists(pkgs_file):
        with open(pkgs_file) as pkgs_json:
            pkgs = json.load(pkgs_json)
            res.update(pkgs)
            return res
    else:
        print("Warning: {} not found".format(pkgs_file))
    return res


def save_packages(directory, pkgs):
    for versions in pkgs.values():
        for version in versions.values():
            version.pop('dsc', None)
    pkgs_file = os.path.join(directory, PKGS_FILE) if directory else PKGS_FILE
    with open(pkgs_file, 'w') as out:
        json.dump(pkgs, out)


def read_whitelist(whitelist):
    if whitelist:
        if os.path.exists(whitelist):
            with open(whitelist, "r") as whitelist_file:
                return whitelist_file.read().splitlines()
        else:
            sys.exit("File {} not found".format(whitelist))
    return ["zlib", "anna", "dpkg"]


def save_to_directory(pkgs, directory):
    if directory:
        for pkg in pkgs:
            name = pkg['Source']
            version = pkg['Version']
            prefix = find_deb_prefix(name)
            dsc = "{}_{}.dsc".format(name, version)
            dest_dir = os.path.join(directory, prefix, name, version)
            dest_filename = os.path.join(dest_dir, dsc)
            os.makedirs(dest_dir, exist_ok=True)
            with open(dest_filename, "w") as dsc_file:
                dsc_file.write(pkg['dsc'])


def main():
    args = get_args()
    if args.directory:
        os.makedirs(args.directory, exist_ok=True)
    pkgs = load_packages(args.directory)
    whitelist = None if args.all else read_whitelist(args.whitelist)
    if args.in_topic or args.debug:  # We should use Kafka
        plugin = DSCAnalyzerKafkaPlugin(
            args.bootstrap_servers, args.in_topic, args.out_topic,
            args.log_topic, args.err_topic, args.group, args.directory,
            args.debug, pkgs, whitelist, args.releases_dir
        )
        if args.debug:
            record = ast.literal_eval(args.debug)
            plugin.consume(record)
        else:
            # Run forever
            while True:
                plugin.consume_messages()
                time.sleep(args.sleep_time)
    else:
        for timestamp in args.timestamps:
            print("{}: begin".format(timestamp))
            pkgs, new_pkgs_counter, new_revisions = process_sources_gz(
                args.archive, timestamp, args.distribution,
                args.component, pkgs, whitelist, args.releases_dir
            )
            save_to_directory(new_revisions, args.directory)
            save_packages(args.directory, pkgs)
            for pkg in new_revisions:
                print("{} {}".format(pkg['Source'], pkg['Version']))
            print("{}: New packages: {}, New revisions: {}".format(
                timestamp, new_pkgs_counter, len(new_revisions)))


if __name__ == "__main__":
    main()
