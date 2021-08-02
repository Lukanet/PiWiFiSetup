#!/usr/bin/env python3
from flask import Flask, render_template, request, redirect
import subprocess
import os
import time
from threading import Thread
import fileinput
import tempfile

app = Flask(__name__)

@app.route('/')
def index():
    wifi_ap_array = scan_wifi_networks()

    return render_template('app.html', wifi_ap_array = wifi_ap_array, config_hash = app.config_hash)


@app.route('/manual_ssid_entry')
def manual_ssid_entry():
    return render_template('manual_ssid_entry.html')

@app.route('/wpa_settings')
def wpa_settings():
    return render_template('wpa_settings.html', wpa_enabled = app.config_hash['wpa_enabled'], wpa_key = app.config_hash['wpa_key'])


@app.route('/save_credentials', methods = ['GET', 'POST'])
def save_credentials():
    ssid = request.form['ssid']
    wifi_key = request.form['wifi_key']

    create_wpa_supplicant(ssid, wifi_key)
    
    # shutdown
    func = request.environ.get('werkzeug.server.shutdown')
    if func is None:
        raise RuntimeError('Not running with the Werkzeug Server')
    func()

    return render_template('save_credentials.html', ssid = ssid)


@app.route('/save_wpa_credentials', methods = ['GET', 'POST'])
def save_wpa_credentials():
    wpa_enabled = request.form.get('wpa_enabled')
    wpa_key = request.form['wpa_key']

    if str(wpa_enabled) == '1':
        update_wpa(1, wpa_key)
    else:
        update_wpa(0, wpa_key)

    return render_template('save_wpa_credentials.html', wpa_enabled = app.config_hash['wpa_enabled'], wpa_key = app.config_hash['wpa_key'])

@app.route('/<path:path>')
def catch_all(path):
    return redirect('/')

######## FUNCTIONS ##########

def scan_wifi_networks():
    iwlist_raw = None
    i = 0
    while (not iwlist_raw or iwlist_raw.returncode != 0) and i < 10:
        iwlist_raw = subprocess.run(['iwlist', 'wlan0', 'scan'], capture_output=True)
        i = i + 1 
        if iwlist_raw.returncode != 0:
            print(iwlist_raw.stderr)
            time.sleep(1)

    ap_array = []
    for line in iwlist_raw.stdout.decode('utf-8').rsplit('\n'):
        if 'ESSID' in line:
            ap_ssid = line[27:-1]
            if ap_ssid != '':
                ap_array.append(ap_ssid)

    return ap_array

def create_wpa_supplicant(ssid, wifi_key):
    # edit inplace
    if wifi_key == '':
        wifi_key_line = '	key_mgmt=NONE'
    else:
        wifi_key_line = '	psk="' + wifi_key + '"'
    
    in_network = 0
    wpa_file = '/etc/wpa_supplicant/wpa_supplicant.conf'
    with fileinput.FileInput(wpa_file, inplace=True) as wpa_supplicant:
        for line in wpa_supplicant:
            if in_network == 1:
                if 'ssid=' in line:
                    line_array = line.split('=')
                    line_array[1] = ssid
                    print(line_array[0] + '="' + str(line_array[1]) + '"')
                elif 'key_mgmt=NONE' in line or 'psk=' in line:
                    print(wifi_key_line)
                else:
                    print(line, end='')
                    if '}' in line:
                        in_network = 2
            else:
                print(line, end='')
            if 'network=' in line and in_network < 2:
                in_network = 1
    if not in_network:
        wpa_h = open(wpa_file, 'a')
        wpa_h.write('network={\n')
        wpa_h.write('	ssid="' + ssid + '"\n')
        wpa_h.write(wifi_key_line + '\n')
        wpa_h.write('}' + '\n')
        wpa_h.close()

def update_wpa(wpa_enabled, wpa_key):
    app.config_hash['wpa_enabled'] = str(wpa_enabled)
    app.config_hash['wpa_key'] = str(wpa_key)

    # restart hostapd
    start_hostapd()

    # Create the config if it doesn't exists
    if not os.path.isfile(app.config_file):
        open(app.config_file, 'w').close()

    # edit inplace
    with fileinput.FileInput(app.config_file, inplace=True) as raspiwifi_conf:
        wpa_enabled_set = False
        wpa_key_set = False
        for line in raspiwifi_conf:
            if 'wpa_enabled=' in line:
                line_array = line.split('=')
                line_array[1] = wpa_enabled
                print(line_array[0] + '=' + str(line_array[1]))
                wpa_enabled_set = True

            if 'wpa_key=' in line:
                line_array = line.split('=')
                line_array[1] = wpa_key
                print(line_array[0] + '=' + line_array[1])
                wpa_key_set = True

            if 'wpa_enabled=' not in line and 'wpa_key=' not in line:
                print(line, end='')

    # if the settings are not found we add them
    if not wpa_enabled_set or not wpa_key_set:
        config_file = open(app.config_file, 'a')
        if not wpa_enabled_set:
            config_file.write('wpa_enabled=' + str(wpa_enabled) + '\n')
        if not wpa_key_set:
            config_file.write('wpa_key=' + str(wpa_key) + '\n')
        config_file.close()


def config_file_hash():
    #defaults
    config_hash = {'ssid_prefix': 'Pi Wifi Setup',
                   'wpa_enabled': '1', 
                   'wpa_key': '1234567890'}
    if os.path.isfile(app.config_file):
        config_file = open(app.config_file)

        for line in config_file:
            line_key = line.split("=")[0]
            line_value = line.split("=")[1].rstrip()
            config_hash[line_key] = line_value

    return config_hash

# Just prints out from the process
def output_reader(proc):
    for line in iter(proc.stdout.readline, b''):
        print('{1}[{2}]: {0}'.format(line.decode('utf-8'), proc.args[0], proc.pid), end='')

def start_hostapd():
    if app.hostapd:
        app.hostapd.terminate()
        app.hostapd_conf.close()
        time.sleep(2)

    app.hostapd_conf = tempfile.NamedTemporaryFile(mode='w')
    app.hostapd_conf.writelines(['interface=wlan0\n',
                                 'driver=nl80211\n',
                                 'channel=1\n'])
    app.hostapd_conf.write('ssid=' + app.config_hash['ssid_prefix'] + '\n')
    if app.config_hash['wpa_enabled'] == '1':
        app.hostapd_conf.writelines(['auth_algs=1\n',
                                     'wpa=2\n',
                                     'wpa_key_mgmt=WPA-PSK\n',
                                     'rsn_pairwise=CCMP\n',
                                     'wpa_passphrase=' + app.config_hash['wpa_key'] + '\n'])
    app.hostapd_conf.flush()
    app.hostapd = subprocess.Popen(['hostapd', app.hostapd_conf.name],
                        stdout=subprocess.PIPE,
                        stderr=subprocess.STDOUT)
    t = Thread(target=output_reader, args=(app.hostapd,))
    t.start()


def main():
    app.debug = True
    app.config_file = '/etc/PiWiFiSetup/PiWiFiSetup.conf'
    app.config_hash = config_file_hash()
    app.hostapd = None

    # Stop dhcpcd and dnsmasq so they don't interfere
    subprocess.check_call(['systemctl', 'stop', 'dnsmasq.service'])

    # Setup the ip address
    subprocess.check_call(['rfkill','unblock','wlan'])
    subprocess.check_call(['ip','address','add', '10.0.0.1/24', 'dev', 'wlan0'])

    # start hostapd
    start_hostapd()

    # wait for hostap to start and setup wlan0
    time.sleep(1)

    # Start dnsmasq
    dnsmasq = subprocess.Popen(['dnsmasq', '-C', '/dev/null', '--no-daemon', 
                                        '--interface','wlan0',
                                        '--bind-interfaces',
                                        '--except-interface','lo',
                                        '--dhcp-range','10.0.0.10,10.0.0.15,12h',
                                        '--address','/#/10.0.0.1',
                                        '--no-resolv',
                                        '--no-hosts'
                                        ],
                        stdout=subprocess.PIPE,
                        stderr=subprocess.STDOUT)
    t = Thread(target=output_reader, args=(dnsmasq,))
    t.start()

    # I didn't figure out a way to use the reloader and have the hostapd and dnsmasq subprocess working
    app.run(host = '10.0.0.1', port = 80, use_reloader=False)

    # Cleanup
    app.hostapd.terminate()
    app.hostapd_conf.close()
    dnsmasq.terminate()
    subprocess.check_call(['ip','address','del', '10.0.0.1/24', 'dev', 'wlan0'])
    subprocess.check_call(['systemctl', 'daemon-reload'])
    subprocess.check_call(['systemctl', 'restart', 'wpa_supplicant.service', 'dhcpcd.service'])
    subprocess.check_call(['systemctl', 'start', 'dnsmasq.service'])

if __name__ == '__main__':
    main()
