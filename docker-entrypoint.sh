#!/bin/bash
set -euo pipefail

# Load pulseaudio virtual audio source
pulseaudio -D --exit-idle-time=-1

pacmd load-module module-virtual-sink sink_name=v1  # Load a virtual sink as `v1`
pacmd set-default-sink v1  # Set the `v1` as the default sink device
pacmd set-default-source v1.monitor  # Set the monitor of the v1 sink to be the default source

pacmd load-module module-native-protocol-tcp auth-ip-acl=127.0.0.1

exec "$@"