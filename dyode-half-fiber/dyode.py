1# -*- coding: utf-8 -*-

import datetime
import errno
import hashlib
import logging
import multiprocessing
from multiprocessing import Process, Pipe, Queue
import os
import random
import shlex
import shutil
# Imports
import string
import subprocess
import time
import json

# Logging stuff
logging.basicConfig()
global log
log = logging.getLogger()
log.setLevel(logging.DEBUG)


######################## Reception specific functions ##########################

def parse_manifest(file_path, in_path, out_path):
    log.debug("config file:" + file_path)
    files = []
    dirs = []
    with open(file_path, 'r') as config_file:
        try:
            data = json.load(config_file)
            # for file_path, file_hash in data['files']:
            #     log.debug(file_path + ' :: ' + file_hash())
            #     files[file_path] = file_hash
            files = data['files']
            dirs = data['dirs']
            if in_path != out_path:
                t = []
                for f in files:
                    t.append(out_path + os.path.relpath(f, in_path))
                files = t
                t = []
                for d in dirs:
                    t.append(out_path + os.path.relpath(d, in_path))
                dirs = t
        except:
            pass
    return dirs, files


def check_hash_process(queue):
    while True:
        temp_file, hash_list, success_log, failure_log = queue.get()
        log.debug("check hash for :: %s at %s" % (temp_file, datetime.datetime.now()))
        if hash_list is None:
            if temp_file is None:
                break
            else:
                for the_file in os.listdir(temp_file):
                    file_path = os.path.join(temp_file, the_file)
                    if os.path.isdir(file_path):
                        shutil.rmtree(file_path)
                    else:
                        os.remove(file_path)
                continue
        h = hash_file(temp_file)
        if h not in hash_list:
            log.error('Invalid checksum for file ' + temp_file + " " + h)
            with open(failure_log, 'at') as f: # remove b in (ab)
                f.write(h + ' ' + temp_file + '\n')
            os.remove(temp_file)
        else:
            f = hash_list[h]
            file_path = os.path.dirname(f)
            if not os.path.exists(file_path):
                try:
                    os.makedirs(file_path)
                except OSError as exc:  # Guard against race condition
                    if exc.errno != errno.EEXIST:
                        raise
            shutil.move(temp_file, f)
            log.info('File Available: ' + f)
            with open(failure_log, 'at') as ffile: # remove b in (ab)
                #f.write(h + ' ' + f + '\n')
                ffile.write(h + ' ' + f + '\n')
    queue.put(None)


# File reception forever loop
def file_reception_loop(params):
    # background hash check
    queue = Queue()

    hash_p = Process(target=check_hash_process, args=(queue,))
    hash_p.daemon = True
    hash_p.start()

    while True:
        wait_for_file(queue, params)
        # time.sleep(0.1)

    queue.put((None,))
    sender.close()
    hash_p.join()
    if hash_p.is_alive():
        hash_p.terminate()
    del receiver, sender, hash_p


# Launch UDPCast to receive a file
def receive_file(file_path, interface, ip_in, port_base, timeout=0):
    command = "udp-receiver --nosync --mcast-rdv-addr {0} --interface {1} --portbase {2} -f '{3}'".format(
        ip_in, interface, port_base, file_path)
    if timeout > 0:
        command = command + " --start-timeout {0} --receive-timeout {0}".format(timeout)
    log.debug(command)
    (output, err) = subprocess.Popen(shlex.split(command), shell=False, stdout=subprocess.PIPE,
                                     stderr=subprocess.PIPE).communicate()


# File reception function
def wait_for_file(queue, params):
    log.debug('Waiting for file ...')
    # Use a dedicated name for each process to prevent race conditions
    process_name = multiprocessing.current_process().name
    if not os.path.exists(params['temp']):
        os.mkdir(params['temp'])
    manifest_filename = params['temp'] + '/manifest_' + process_name + '.json'
    receive_file(manifest_filename, params['interface_out'], params['ip_in'], int(params['port']) + 2)
    dirs, files = parse_manifest(manifest_filename, params['in'], params['out'] + '/')
    if len(files) == 0:
        log.error('No file listed in manifest')
        return 0
    log.debug('Manifest content : %s' % files)

    hash_list = dict()
    for f, h in files:
        hash_list[h] = f

    for f, h in files:
        # filename = os.path.basename(f)
        # mkdir on the fly
        temp_file = params['temp'] + '/' + ''.join(
            random.SystemRandom().choice(string.ascii_uppercase + string.digits) for _ in range(12))
        receive_file(temp_file, params['interface_out'], params['ip_in'], params['port'], 10)
        log.info('File ' + temp_file + ' received at ' + str(datetime.datetime.now()))
        if os.path.exists(temp_file):
            queue.put((temp_file, hash_list,
                       params['out'] + '/transfer_success.log',
                       params['out'] + '/transfer_failure.log'))

    os.remove(manifest_filename)
    # todo: background
    queue.put((params['temp'], None, None, None))


################### Send specific functions ####################################

# Send a file using udpcast
def send_file(file_path, interface, ip_out, port_base, max_bitrate):
    # 10.0.1.2
    command = 'udp-sender --async --fec 8x8 --max-bitrate {:0.0f}m '.format(max_bitrate) \
              + '--mcast-rdv-addr {0} --mcast-data-addr {0} '.format(ip_out) \
              + '--portbase {0} --autostart 1 '.format(port_base) \
              + "--interface {0} -f '{1}'".format(interface, file_path)
    log.debug(command)
    (output, err) = subprocess.Popen(command, stdout=subprocess.PIPE, shell=True).communicate()
    time.sleep(1.5)


# List all files recursively
def list_all_files(root_dir):
    files = []
    dirs = []  # [root_dir]
    for root, directories, filenames in os.walk(root_dir):
        for directory in directories:
            dirs.append(os.path.join(root, directory))
        for filename in filenames:
            files.append(os.path.join(root, filename))

    return dirs, files


def write_manifest(dirs, files, files_hash, manifest_filename, root, new):
    data = {'dirs': [d.replace(root, new, 1) for d in dirs], 'files': []}
    log.debug([d.replace(root, new, 1) for d in dirs])
    for f in files:
        data['files'].append([f.replace(root, new, 1), files_hash[f]])
        log.debug(f + ' :: ' + files_hash[f])

    with open(manifest_filename, 'w') as configfile: # remove b in (wb)
        json.dump(data, configfile)


def file_copy(params):
    # TODO: send existing file (startup service) : not open
    delete = True
    if 'delete' in params and params['delete'] == 'no':
        delete = False
    log.debug('Local copy starting ... with params :: %s', params)

    dirs, files = list_all_files(params[1]['in'])
    if len(files) == 0:
        log.debug('No file detected')
        return 0
    manifest_data = {}

    for f in files:
        if os.path.isfile(f):
            manifest_data[f] = hash_file(f)
    log.debug('Writing manifest file')
    # Use a dedicated name for each process to prevent race conditions
    manifest_filename = 'manifest_' + str(params[0]) + '.json'
    write_manifest(dirs, files, manifest_data, manifest_filename, params[1]['in'], params[1]["out"])
    log.info('Sending manifest file : ' + manifest_filename)

    log.debug(datetime.datetime.now())
    send_file(manifest_filename,
              params[1]['interface_in'],
              params[1]['ip_out'],
              int(params[1]['port']) + 2,
              params[1]['bitrate'])
    log.debug('Deleting manifest file')
    os.remove(manifest_filename)
    for f in files:
        log.info('Sending: ' + f)
        log.debug(datetime.datetime.now())
        send_file(f,
                  params[1]['interface_in'],
                  params[1]['ip_out'],
                  params[1]['port'],
                  params[1]['bitrate'])
        log.info('Deleting: ' + f)
        if delete:
            os.remove(f)
    if delete:
        for d in dirs:
            log.info('Deleting Dir: ' + d)
            try:
                os.rmdir(d)
            except:
                pass


########################### Shared functions ###################################

def hash_file(file):
    # TODO: use 'sha256sum' command for speedup ?
    BLOCKSIZE = 65536
    hasher = hashlib.sha256()
    with open(file, 'rb') as afile:
        buf = afile.read(BLOCKSIZE)
        while len(buf) > 0:
            hasher.update(buf)
            buf = afile.read(BLOCKSIZE)

    return hasher.hexdigest()
