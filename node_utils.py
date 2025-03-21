import json
import sys
import argparse
import subprocess
from functools import reduce
from prettytable import PrettyTable
from datetime import datetime
import wcwidth  # Add wcwidth to handle double-width characters

def convert_timestamp_to_age(timestamp):
    current_time = int(datetime.now().timestamp())
    return current_time - int(timestamp)

def format_duration(seconds):
    days = seconds // (24 * 3600)
    seconds %= (24 * 3600)
    hours = seconds // 3600
    seconds %= 3600
    minutes = seconds // 60
    seconds %= 60
    parts = []
    if days > 0:
        parts.append(f"{days}d")
    if hours > 0:
        parts.append(f"{hours}h")
    if minutes > 0:
        parts.append(f"{minutes}m")
    if seconds > 0 or not parts:
        parts.append(f"{seconds}s")
    return " ".join(parts)

def flatten(lst):
    return [item for sublist in lst for item in (flatten(sublist) if isinstance(sublist, list) else [sublist])]

def remove_inactive_nodes(data, meshtastic_flags):
    for key, value in data.items():
        if 'isFavorite' not in value and ('lastHeard' in value and 'lastHeardRaw' in value and value['lastHeardRaw'] > 3600) or 'lastHeard' not in value:
            user_id = value['user']['id']
            command = ["meshtastic"]
            if meshtastic_flags:
                command.extend(meshtastic_flags.split(" "))
            command.extend(["--remove-node", user_id])
            print(f"removing node: {value['user']['longName']}")
            result = subprocess.run(command, capture_output=True, text=True)
            if result.returncode != 0:
                print(result.stderr)

def process_meshtastic_output(output):
    lines = output.splitlines()
    start_index = None
    end_index = None

    lines = [line for line in lines if line.strip()]
    for i, line in enumerate(lines):
        if "Nodes in mesh" in line:
            start_index = i
        if "Preferences" in line:
            end_index = i - 1
            break

    if start_index is not None and end_index is not None:
        json_lines = lines[start_index:end_index + 1]
        json_lines[0] = "{"
        json_text = "\n".join(json_lines)
        return json_text
    return None

def add_column_if_flag(columns, flag, column_name):
    if flag:
        columns.append(column_name)

def add_value_if_column(row, columns, column_name, value):
    if column_name in columns:
        row.append(value)

def calculate_display_width(text):
    return sum(wcwidth.wcwidth(char) for char in text)

def main():
    parser = argparse.ArgumentParser(description="Replace lastHeard field with age and display JSON as table.")
    parser.add_argument('--fullname', action='store_true', help="Display user.longName column")
    parser.add_argument('--shortname', action='store_true', help="Display user.shortName column")
    parser.add_argument('--macaddr', action='store_true', help="Display user.macaddr column")
    parser.add_argument('--hwmodel', action='store_true', help="Display user.hwModel column")
    parser.add_argument('--publickey', action='store_true', help="Display user.publicKey column")
    parser.add_argument('--num', action='store_true', help="Display num column")
    parser.add_argument('--snr', action='store_true', help="Display snr column")
    parser.add_argument('--batteryLevel', action='store_true', help="Display deviceMetrics.batteryLevel column")
    parser.add_argument('--voltage', action='store_true', help="Display deviceMetrics.voltage column")
    parser.add_argument('--channelUtilization', action='store_true', help="Display deviceMetrics.channelUtilization column")
    parser.add_argument('--airUtilTx', action='store_true', help="Display deviceMetrics.airUtilTx column")
    parser.add_argument('--uptimeSeconds', action='store_true', help="Display deviceMetrics.uptimeSeconds column")
    parser.add_argument('--hopsAway', action='store_true', help="Display hopsAway column")
    parser.add_argument('--isFavorite', action='store_true', help="Display isFavorite column")
    parser.add_argument('--latitude', action='store_true', help="Display position.latitude column")
    parser.add_argument('--longitude', action='store_true', help="Display position.longitude column")
    parser.add_argument('--altitude', action='store_true', help="Display position.altitude column")
    parser.add_argument('--positionLatitudeI', action='store_true', help="Display position.latitudeI column")
    parser.add_argument('--positionLongitudeI', action='store_true', help="Display position.longitudeI column")
    parser.add_argument('--positionTime', action='store_true', help="Display position.time column")
    parser.add_argument('--locationSource', action='store_true', help="Display position.locationSource column")
    parser.add_argument('--lastheard', action='store_true', help="Display lastHeard column")
    parser.add_argument('--remove-inactive', action='store_true', help="Remove inactive nodes (lastHeard > 1h and not isFavorite)")
    parser.add_argument('--meshtastic', type=str, default="", help="Meshtastic command to run")
    parser.add_argument('--json', action='store_true', help="print json instead")

    args = parser.parse_args()

    meshtastic_command = ["meshtastic"]
    meshtastic_command.extend(args.meshtastic.split() + ['--info'])
    result = subprocess.run(meshtastic_command, capture_output=True, text=True)
    if result.returncode != 0:
        print(f"Error running meshtastic command: {result.stderr}", file=sys.stderr)
        sys.exit(1)
    output = result.stdout
    import re
    myNodeNum = re.search(r'"myNodeNum": (\d+)', output).group(1)
    json_text = process_meshtastic_output(output)
    if json_text:
        data = json.loads(json_text)
    else:
        print("Failed to extract JSON from meshtastic output.")
        sys.exit(1)
    
    if args.json:
        print(json.dumps(data, indent=2))
        sys.exit(0)

    # Replace lastHeard with age and store raw age for filtering
    for key, value in data.items():
        if 'lastHeard' in value:
            value['lastHeardRaw'] = convert_timestamp_to_age(value['lastHeard'])
            value['lastHeard'] = format_duration(value['lastHeardRaw'])

    # Remove inactive nodes if the flag is set
    if args.remove_inactive:
        remove_inactive_nodes(data, args.meshtastic)
        # Filter out inactive nodes from the display
        data = {k: v for k, v in data.items() if 'lastHeardRaw' not in v or v['lastHeardRaw'] <= 3600}

    data = sorted(data.items(), key=lambda item: item[1].get('lastHeardRaw', float('inf')))
    if args.hopsAway:
        data = sorted(data, key=lambda item: item[1].get('hopsAway', float('inf')))

    # Prepare data for the table
    table = PrettyTable()

    columns = ['longName', 'lastHeard']
    add_column_if_flag(columns, args.shortname, 'shortName')
    add_column_if_flag(columns, args.macaddr, 'macaddr')
    add_column_if_flag(columns, args.hwmodel, 'hwModel')
    add_column_if_flag(columns, args.publickey, 'publicKey')
    add_column_if_flag(columns, args.num, 'num')
    add_column_if_flag(columns, args.snr, 'snr')
    add_column_if_flag(columns, args.batteryLevel, 'batteryLevel')
    add_column_if_flag(columns, args.voltage, 'voltage')
    add_column_if_flag(columns, args.channelUtilization, 'channelUtilization')
    add_column_if_flag(columns, args.airUtilTx, 'airUtilTx')
    add_column_if_flag(columns, args.uptimeSeconds, 'uptimeSeconds')
    add_column_if_flag(columns, args.hopsAway, 'hopsAway')
    add_column_if_flag(columns, args.isFavorite, 'isFavorite')
    add_column_if_flag(columns, args.latitude, 'latitude')
    add_column_if_flag(columns, args.longitude, 'longitude')
    add_column_if_flag(columns, args.altitude, 'altitude')
    add_column_if_flag(columns, args.positionLatitudeI, 'latitudeI')
    add_column_if_flag(columns, args.positionLongitudeI, 'longitudeI')
    add_column_if_flag(columns, args.positionTime, 'time')
    add_column_if_flag(columns, args.locationSource, 'locationSource')

    table.field_names = columns

    for key, value in data:
        if int(value['num']) == int(myNodeNum):
            continue
        row = []
        row.append(value['user']['longName'])
        row.append(value.get('lastHeard', 'N/A'))
        add_value_if_column(row, columns, 'shortName', value['user'].get('shortName', 'N/A'))
        add_value_if_column(row, columns, 'macaddr', value['user'].get('macaddr', 'N/A'))
        add_value_if_column(row, columns, 'hwModel', value['user'].get('hwModel', 'N/A'))
        add_value_if_column(row, columns, 'publicKey', value['user'].get('publicKey', 'N/A'))
        add_value_if_column(row, columns, 'num', value.get('num', 'N/A'))
        add_value_if_column(row, columns, 'snr', value.get('snr', 'N/A'))
        add_value_if_column(row, columns, 'batteryLevel', value.get('deviceMetrics', {}).get('batteryLevel', 'N/A'))
        add_value_if_column(row, columns, 'voltage', value.get('deviceMetrics', {}).get('voltage', 'N/A'))
        add_value_if_column(row, columns, 'channelUtilization', value.get('deviceMetrics', {}).get('channelUtilization', 'N/A'))
        add_value_if_column(row, columns, 'airUtilTx', value.get('deviceMetrics', {}).get('airUtilTx', 'N/A'))
        add_value_if_column(row, columns, 'uptimeSeconds', value.get('deviceMetrics', {}).get('uptimeSeconds', 'N/A'))
        add_value_if_column(row, columns, 'hopsAway', value.get('hopsAway', 'N/A'))
        add_value_if_column(row, columns, 'isFavorite', value.get('isFavorite', 'N/A'))
        add_value_if_column(row, columns, 'latitude', value.get('position', {}).get('latitude', 'N/A'))
        add_value_if_column(row, columns, 'longitude', value.get('position', {}).get('longitude', 'N/A'))
        add_value_if_column(row, columns, 'altitude', value.get('position', {}).get('altitude', 'N/A'))
        add_value_if_column(row, columns, 'latitudeI', value.get('position', {}).get('latitudeI', 'N/A'))
        add_value_if_column(row, columns, 'longitudeI', value.get('position', {}).get('longitudeI', 'N/A'))
        add_value_if_column(row, columns, 'time', value.get('position', {}).get('time', 'N/A'))
        add_value_if_column(row, columns, 'locationSource', value.get('position', {}).get('locationSource', 'N/A'))

        table.add_row(row)

    # Set the proper width for the longName column
    max_longname_width = max(calculate_display_width(row[0]) for row in table._rows)
    table.max_width['longName'] = max_longname_width

    if not args.remove_inactive:
      print(table.get_string())

if __name__ == "__main__":
    main()
