#!/usr/bin/env python3
import time
from xarm.wrapper import XArmAPI

arm = XArmAPI('192.168.1.177', baud_checkset=False)
arm.motion_enable(True)
arm.set_mode(0)
arm.set_state(0)

TABLE_Z = 59.81

print('=' * 40)
print('  Arm Height Controller')
print('  TABLE_Z = {:.2f}mm'.format(TABLE_Z))
print('  First move arm to safe position')
print('  manually in Studio, then run.')
print('  Type Q to quit')
print('=' * 40)

print('\n>> Move the arm to your safe starting position in Studio,')
print('   then press ENTER when ready...')
input()

# Read current position as the safe reference
ret = arm.get_position()
if ret[0] != 0:
    print('>> ERROR: Could not read position.')
    arm.disconnect()
    exit()

ref_x    = ret[1][0]
ref_y    = ret[1][1]
ref_z    = ret[1][2]
ref_roll  = ret[1][3]
ref_pitch = ret[1][4]
ref_yaw   = ret[1][5]

print('\n>> Safe reference position locked:')
print('   X={:.2f}  Y={:.2f}  Z={:.2f}'.format(ref_x, ref_y, ref_z))
print('   Roll={:.2f}  Pitch={:.2f}  Yaw={:.2f}'.format(ref_roll, ref_pitch, ref_yaw))
print('   Currently {:.2f}mm above table'.format(ref_z - TABLE_Z))

while True:
    user_input = input('\n>> Enter height above table in mm (or Q to quit): ').strip().lower()

    if user_input == 'q':
        print('>> Exiting.')
        break

    try:
        height = float(user_input)
    except ValueError:
        print('>> Invalid input — enter a number in mm.')
        continue

    if height < 0:
        print('>> Height must be 0 or above — cannot go below the table!')
        continue

    if height < 5:
        print('>> WARNING: Less than 5mm above table. Confirm? (Y/N): ', end='')
        if input().strip().lower() != 'y':
            print('>> Cancelled.')
            continue

    target_z = TABLE_Z + height

    print('\n>> Moving to {:.2f}mm above table (Z={:.2f}mm)...'.format(height, target_z))

    # Move only Z, keep everything else exactly as the reference
    code = arm.set_position(
        x=ref_x, y=ref_y, z=target_z,
        roll=ref_roll, pitch=ref_pitch, yaw=ref_yaw,
        speed=50, mvacc=500,
        wait=True)

    if code == 0:
        ret = arm.get_position()
        if ret[0] == 0:
            actual_z = ret[1][2]
            actual_distance = actual_z - TABLE_Z
            print('>> Reached position!')
            print('   Target:  {:.2f}mm above table'.format(height))
            print('   Actual:  {:.2f}mm above table (Z={:.2f}mm)'.format(actual_distance, actual_z))
    else:
        print('>> ERROR: Move failed with code {}'.format(code))

arm.disconnect()
print('>> Disconnected.')