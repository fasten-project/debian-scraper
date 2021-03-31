# snapshot.debian.org scraper

This Python script scrapes [snapshot.debian.org](https://snapshot.debian.org/),
and it either forwards it to Kafka or saves results to a local file.
The scraper script provides a command-line interface with many abilities,
and it can be extended easily.
First, it downloads a .dsc file for a Debian release,
then it parses the source packages from the dsc file,
and finally, it saves the result in pkgs.json.

## Prerequisites

Install all dependencies:

```bash
python3 -m venv venv
. ./venv/bin/activate
pip install pycurl fasten
```

## How To Run

```bash
python3 entrypoint.py --help
usage: DSC Analyzer [-h] [-d DIRECTORY] [--releases-dir RELEASES_DIR]
                    [-w WHITELIST] [-D DEBUG] [-A]
                    [-t TIMESTAMPS [TIMESTAMPS ...]]
                    [--distribution DISTRIBUTION] [-a ARCHIVE]
                    [-c COMPONENT] [-s SINGLE_PACKAGE] [-u URL]
                    [-i IN_TOPIC] [-o OUT_TOPIC] [-e ERR_TOPIC] [-l LOG_TOPIC]
                    [-b BOOTSTRAP_SERVERS] [-g GROUP] [--sleep-time SLEEP_TIME]

Download and analyze Debian Source Control Files from snapshot.d.o.

optional arguments:
  -h, --help            show this help message and exit
  -d DIRECTORY, --directory DIRECTORY
                        Path to base directory where dsc files, and state will
                        be saved.
  --releases-dir RELEASES_DIR
                        Path to directory where dsc files for releases will be
                        saved.
  -w WHITELIST, --whitelist WHITELIST
                        File with Debian package names to process
  -D DEBUG, --debug DEBUG
                        Debug mode for testing Kafka implementation.
  -A, --all             Do not use a whitelist
  -t TIMESTAMPS [TIMESTAMPS ...], --timestamps TIMESTAMPS [TIMESTAMPS ...]
                        A list of timestamps (default: timestamps for releases
                        of Debian buster.
  --distribution DISTRIBUTION
                        Debian distribution (Default: buster)
  -a ARCHIVE, --archive ARCHIVE
                        Debian archive (Default: debian)
  -c COMPONENT, --component COMPONENT
                        Debian component (Default: main)
  -s SINGLE_PACKAGE, --single-package SINGLE_PACKAGE
                        Parse a single package (You must provide a url with --url option)
  -u URL, --url URL     Provide a URL for downloading a single file.
                        It will ignore the options --archive, --component,
                        --distribution, --timestamps.
  -i IN_TOPIC, --in-topic IN_TOPIC
                        Kafka topic to read from.
  -o OUT_TOPIC, --out-topic OUT_TOPIC
                        Kafka topic to write to.
  -e ERR_TOPIC, --err-topic ERR_TOPIC
                        Kafka topic to write errors to.
  -l LOG_TOPIC, --log-topic LOG_TOPIC
                        Kafka topic to write logs to.
  -b BOOTSTRAP_SERVERS, --bootstrap-servers BOOTSTRAP_SERVERS
                        Kafka servers, comma separated.
  -g GROUP, --group GROUP
                        Kafka consumer group to which the consumer belongs.
  --sleep-time SLEEP_TIME
                        Time to sleep in between each consuming (in sec) --
                        only with -i.
```

**Examples**

* Get all c packages releases from Buster releases and save them in `pkgs.json`.
The default option will be used:
    - Distribution: buster
    - Archive: debian
    - Component: main
    - Whitelist: zlib, anna, dpkg
    - Timestamps: 20190707T211830Z, 20190908T222211Z, 20191117T204416Z,
    20200209T205554Z, 20200510T203930Z, 20200802T204950Z, 20200927T204254Z,
    20201206T204150Z, 20210207T205150Z, 20210328T030002Z

```bash
python entrypoint.py --whitelist c_packages.txt
```

* Run in Kafka debug mode and save dsc files with docker

```bash
docker run -it --privileged -v $(pwd)/temp/debug:/root/debug \
    -v $(pwd)/temp/dsc:/mnt/fasten/dsc kafka-dscanalyzer \
    --whitelist c_packages.txt \
    --directory /mnt/fasten/dsc \
    --debug "{'timestamp': '20190707T211830Z', 'archive': 'debian', 'distribution': 'buster', 'component': 'main'}"
```

* Feed messages to Kafka topic and run Kafka plugin.

```bash
# We will use in_topic and out_topic as the topics to be used
echo '{"timestamp": "20190707T211830Z", "archive": "debian", "distribution": "buster", "component": "main"}' > \
    kafka-console-producer --broker-list localhost:9092 --topic in_topic
docker run -it --net=host --privileged dscanalyzer \
    -i in_topic -o out_topic -e err_topic -l log_topic \
    -b localhost:9092 -g group-1 -s 60
```

## Run in Docker

```bash
docker build -t kafka-dscanalyzer .
docker run kafka-dscanalyzer --help
```

or alternatively

```bash
# If use it with kafka pass to docker: --net=host
docker run kafka-dscanalyzer --help
```

## Sample data

Produced data format.

```json
{
    "source": "dpkg",
    "version": "1.19.7",
    "release": "buster",
    "arch": "amd64",
    "forge": "debian",
    "dsc": {
      "Source": "dpkg",
      "Binary": [
        "dpkg",
        "libdpkg-dev",
        "dpkg-dev",
        "libdpkg-perl",
        "dselect"
      ],
      "Version": "1.19.7",
      "Maintainer": "Dpkg Developers <debian-dpkg@lists.debian.org>",
      "Uploaders": [
        "Guillem Jover <guillem@debian.org>"
      ],
      "Build-Depends": [
        "debhelper (>= 11)",
        "pkg-config",
        "gettext (>= 0.19.7)",
        "po4a (>= 0.43)",
        "zlib1g-dev",
        "libbz2-dev",
        "liblzma-dev",
        "libselinux1-dev [linux-any]",
        "libncurses-dev (>= 6.1+20180210) | libncursesw5-dev",
        "bzip2 <!nocheck>",
        "xz-utils <!nocheck>"
      ],
      "Architecture": [
        "any",
        "all"
      ],
      "Standards-Version": "4.3.0",
      "Format": "3.0 (native)",
      "Files": [
        {
          "checksum": "ccf88c94789772b9a757afff3c58e156",
          "size": "2103",
          "filename": "dpkg_1.19.7.dsc"
        },
        {
          "checksum": "60f57c5494e6dfa177504d47bfa0e383",
          "size": "4716724",
          "filename": "dpkg_1.19.7.tar.xz"
        }
      ],
      "Vcs-Browser": "https://git.dpkg.org/cgit/dpkg/dpkg.git",
      "Vcs-Git": "https://git.dpkg.org/git/dpkg/dpkg.git",
      "Vcs": "https://git.dpkg.org/git/dpkg/dpkg.git",
      "Checksums-Sha256": [
        {
          "checksum": "098b285d5fc7add8972e5b2b3678027bba3f3fe01962e5176db2fbff33bbd8e3",
          "size": "2103",
          "filename": "dpkg_1.19.7.dsc"
        },
        {
          "checksum": "4c27fededf620c0aa522fff1a48577ba08144445341257502e7730f2b1a296e8",
          "size": "4716724",
          "filename": "dpkg_1.19.7.tar.xz"
        }
      ],
      "Homepage": "https://wiki.debian.org/Teams/Dpkg",
      "Package-List": [
        {
          "name": "dpkg",
          "type": "deb",
          "section": "admin",
          "priority": "required",
          "arch": [
            "any"
          ]
        },
        {
          "name": "dpkg-dev",
          "type": "deb",
          "section": "utils",
          "priority": "optional",
          "arch": [
            "all"
          ]
        },
        {
          "name": "dselect",
          "type": "deb",
          "section": "admin",
          "priority": "optional",
          "arch": [
            "any"
          ]
        },
        {
          "name": "libdpkg-dev",
          "type": "deb",
          "section": "libdevel",
          "priority": "optional",
          "arch": [
            "any"
          ]
        },
        {
          "name": "libdpkg-perl",
          "type": "deb",
          "section": "perl",
          "priority": "optional",
          "arch": [
            "all"
          ]
        }
      ],
      "Testsuite": "autopkgtest",
      "Testsuite-Triggers": [
        "autoconf",
        "build-essential",
        "file",
        "pkg-config"
      ],
      "Directory": "pool/main/d/dpkg",
      "Priority": "source",
      "Section": "admin"
    }
  }
}
```
