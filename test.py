ors = []
ool = [122191289319283, 100000, {'order_id': 'abc'}]

nol = [item for item in ool]
nol[1] -= 12388
ors.append(nol)
ool[1] = 12388

print(ors, ool)