#!/bin/sh
cd $(dirname $0)

PROJECT_VERSION=$(cat ../version.txt)

echo Create a base image with all needed the packages for succesfully build
docker build -q --rm -t kraken-prereq -f Dockerfile.prereq .

echo Create build image for version $PROJECT_VERSION
docker build -q --rm -t kraken-build:$PROJECT_VERSION -f Dockerfile.build ..

echo Run build process in docker container
docker run --rm kraken-build:$PROJECT_VERSION

echo Build finished with code $?
