#! /bin/sh
sudo docker build -t debian-scraper -f Dockerfile .
sudo docker tag debian-scraper schaliasos/debian-scraper
