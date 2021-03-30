#! /bin/sh
cd udd-mirror
sudo docker build --no-cache -t debian-scraper -f Dockerfile .
sudo docker tag debian-scraper schaliasos/debian-scraper
cd ../
