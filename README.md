Working on updating the dyode-half-fiber part to python3 

## Done:
* Moving files between proxys

## Todo: 
* Modbus
* OPC UA


# Data Diode

This project improve [data-diode](https://github.com/wavestone-cdt/dyode) project for better service in fast environment.

## Future

* SMB file share
* 1G connection speed ( limit single file transfer to 300 Mb/s for os UDP packet reorder)

## Bug

* sync send and receive step delay

## TODO

* setup udpcast and auto install
* log of file transferred (with log rotate)
* migrate to python 3
* one port for sync and some command
* error log file
* destination folder empty size check
* syslog redirect
* repository (nexus, ubuntu, windows)
* file access: FTP, SFTP, web, ...
* domain access manager for users
* append new manifest to previous file list
* add **rate-limit** and **drop-rate** to udp-redirect
