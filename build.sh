#! /bin/sh
cd udd-mirror
sudo docker build --no-cache -t debian-scraper -f Dockerfile .
sudo docker tag debian-scraper \
    docker.pkg.github.com/fasten-project/debian-scraper/schaliasos/debian-scraper
cd ../
cd udd-mirror
sudo docker build --no-cache -t kafka-dscanalyzer -f Dockerfile .
sudo docker tag kafka-dscanalyzer \
    docker.pkg.github.com/fasten-project/debian-scraper/kafka-dscanalyzer
cd ../
