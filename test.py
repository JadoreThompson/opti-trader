
import random
from datetime import datetime

old_target = None
while True:
    target = int(str(int(datetime.now().timestamp()))[-3:])
    if target % 60 == 0:
        if target != old_target:
            print("Hit a minute: ", random.randint(0, 1000))
            old_target = target
