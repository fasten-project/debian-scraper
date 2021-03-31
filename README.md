# Debian scraper scripts

This repository provides scrapping scripts for Debian Packages.
Currently, there are two scripts:

1. udd-mirror scraper, which fetches packages from
[udd-mirror](https://udd-mirror.debian.net/).
2. snapshot.d.o scraper, which fetches packages from
[snapshot.debian.org](https://snapshot.debian.org/).

Both scripts can be run as standalone scripts and as Kafka consumers/producers.
