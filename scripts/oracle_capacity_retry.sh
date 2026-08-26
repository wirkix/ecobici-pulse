#!/usr/bin/env bash
#
# Retries `oci compute instance launch` for the ecobici-pulse VM until Oracle
# has A1.Flex (or whatever SHAPE below) capacity in your home region, instead
# of manually re-clicking "Create Instance" in the console.
#
# This retries against your ONE existing Oracle account/region -- it's just
# polling a rate-limited resource, which Oracle treats as normal usage (this
# is the same idea community tools like oci-arm-host-capacity-hunter use).
# It does not attempt to bypass account limits, region restrictions, or
# identity verification.
#
# PREREQUISITES
#   - OCI CLI installed and configured (`oci setup config`), OR just run this
#     from the OCI Console's Cloud Shell (top-right icon) -- it comes with
#     the CLI preinstalled and already authenticated, which is the easiest
#     path from Windows and avoids installing/configuring the CLI locally.
#   - Fill in the CONFIG section below with your own OCIDs (see the "how to
#     find these" comments next to each one).
#
# USAGE
#   chmod +x oracle_capacity_retry.sh   # not needed in Cloud Shell
#   ./oracle_capacity_retry.sh
#
# Stop anytime with Ctrl+C -- it launches nothing until a call actually
# succeeds, so interrupting it is always safe.

set -uo pipefail

# ---------------------------------------------------------------------------
# CONFIG -- fill these in before running.
# ---------------------------------------------------------------------------

# oci iam compartment list --all   (use your tenancy/root compartment OCID
# if you haven't created a sub-compartment)
COMPARTMENT_ID="ocid1.tenancy.oc1..aaaaaaaa4hyxmrai67455ipymd6noufiuawhksn3gw7fwwaqti2pgts7o2sq"

# oci iam availability-domain list --compartment-id "$COMPARTMENT_ID"
AVAILABILITY_DOMAIN="LsEc:MX-QUERETARO-1-AD-1"   # e.g. "abCD:US-ASHBURN-AD-1"

# oci network subnet list --compartment-id "$COMPARTMENT_ID" -- use the
# default VCN's public subnet from when you first set up networking.
SUBNET_ID="ocid1.subnet.oc1.mx-queretaro-1.aaaaaaaaowws4lhynwbtb7jtra465vkj3u4epo7vigx3f2pr5azy7yt6qa6a"

# Recovered from your failed Resource Manager job's log
# (ocid1.ormjob...cla.log) -- it had already resolved this for its plan.
# If you ever need to re-derive it (e.g. a newer Ubuntu image comes out):
# oci compute image list --compartment-id "$COMPARTMENT_ID" \
#   --operating-system "Canonical Ubuntu" --shape "$SHAPE" --sort-by TIMECREATED
IMAGE_ID="ocid1.image.oc1.mx-queretaro-1.aaaaaaaaw2vjumtkmeshgug2pewx43g4ajb22ew3is5pfue47jvjsjt2djsq"

# Path to the SSH public key to inject (must exist locally / in Cloud Shell)
SSH_PUBLIC_KEY_FILE="$HOME/ecobici_pulse_oracle.pub"

SHAPE="VM.Standard.A1.Flex"
OCPUS=2
MEMORY_IN_GBS=12
DISPLAY_NAME="ecobici-pulse-vm"

# Base seconds between attempts; a random 0-20s jitter is added each time so
# this doesn't hammer the API on a rigid, bot-like schedule.
POLL_INTERVAL_SECONDS=90

# 0 = retry forever until it succeeds or you Ctrl+C.
MAX_ATTEMPTS=0

# ---------------------------------------------------------------------------

LOG_FILE="./oracle_capacity_retry.log"
attempt=0

log() {
  printf '%s  %s\n' "$(date '+%Y-%m-%d %H:%M:%S')" "$1" | tee -a "$LOG_FILE"
}

for placeholder in "$COMPARTMENT_ID" "$AVAILABILITY_DOMAIN" "$SUBNET_ID" "$IMAGE_ID"; do
  if [[ "$placeholder" == *REPLACE_ME* ]]; then
    echo "Fill in the CONFIG section at the top of this script before running (see the comments above each variable)." >&2
    exit 1
  fi
done

if [[ ! -f "$SSH_PUBLIC_KEY_FILE" ]]; then
  echo "SSH_PUBLIC_KEY_FILE not found: $SSH_PUBLIC_KEY_FILE" >&2
  exit 1
fi

log "Starting capacity retry loop for $SHAPE in $AVAILABILITY_DOMAIN (Ctrl+C to stop)"

while true; do
  attempt=$((attempt + 1))
  if [[ "$MAX_ATTEMPTS" -gt 0 && "$attempt" -gt "$MAX_ATTEMPTS" ]]; then
    log "Reached MAX_ATTEMPTS ($MAX_ATTEMPTS) without success. Exiting."
    exit 1
  fi

  err_file="$(mktemp)"
  ssh_keys_json=$(python3 -c 'import json,sys; print(json.dumps(open(sys.argv[1]).read()))' "$SSH_PUBLIC_KEY_FILE")

  log "Attempt #$attempt: launching instance..."

  if oci compute instance launch \
      --compartment-id "$COMPARTMENT_ID" \
      --availability-domain "$AVAILABILITY_DOMAIN" \
      --shape "$SHAPE" \
      --shape-config "{\"ocpus\": $OCPUS, \"memoryInGBs\": $MEMORY_IN_GBS}" \
      --image-id "$IMAGE_ID" \
      --subnet-id "$SUBNET_ID" \
      --assign-public-ip true \
      --display-name "$DISPLAY_NAME" \
      --metadata "{\"ssh_authorized_keys\": $ssh_keys_json}" \
      --wait-for-state RUNNING \
      --max-wait-seconds 600 \
      > /tmp/oci_launch_success.json 2> "$err_file"; then

    log "SUCCESS on attempt #$attempt. Instance is RUNNING."
    log "Details written to /tmp/oci_launch_success.json"
    echo
    echo "Fetch its public IP with:"
    echo "  oci compute instance list-vnics --instance-id \$(python3 -c \"import json;print(json.load(open('/tmp/oci_launch_success.json'))['data']['id'])\") --query 'data[0].\"public-ip\"' --raw-output"
    rm -f "$err_file"
    exit 0
  fi

  err_output="$(cat "$err_file")"
  rm -f "$err_file"

  if echo "$err_output" | grep -qi "out of host capacity\|outofcapacity"; then
    log "No capacity yet. Will retry."
  elif echo "$err_output" | grep -qi "toomanyrequests\|429"; then
    log "Rate-limited by Oracle's API -- backing off longer than usual."
    sleep 60
  else
    log "Unexpected error (not a capacity issue) -- stopping so you can fix the config:"
    echo "$err_output" | tee -a "$LOG_FILE"
    exit 1
  fi

  jitter=$((RANDOM % 20))
  sleep_for=$((POLL_INTERVAL_SECONDS + jitter))
  log "Sleeping ${sleep_for}s before next attempt..."
  sleep "$sleep_for"
done
