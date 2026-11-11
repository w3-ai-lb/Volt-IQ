# Site Description

The network comprises 7 diesel generators supplying
12 neighbourhood feeders.

Generators (name, capacity in kVA, dispatch priority):
      Boura-2       400 kVA   priority 1
  300-3         300 kVA   priority 5
  Hasan-4       500 kVA   priority 3
  Midhat-5      500 kVA   priority 7
  Nidal-6       500 kVA   priority 6
  Bostan-7      500 kVA   priority 2
  Fares-8       500 kVA   priority 4

Feeders (name, area type, altitude band, average distance from generator):
      Al-Wadi        rural   above_700m    520 m
  Yassine        urban   below_700m    180 m
  Hay Madi       urban   below_700m    240 m
  Machyak        urban   below_700m    150 m
  Mikdad         rural   above_700m    430 m
  Nahi Taqash    rural   above_700m    380 m
  Moawad         urban   below_700m    200 m
  Atieh          urban   below_700m    260 m
  Dajaja         rural   below_700m    340 m
  Abou Marwan    rural   above_700m    470 m
  Majma Zein     urban   below_700m    190 m
  Harjali        rural   above_700m    410 m

Feeder names on the InteliATS controllers correspond to the zone names in
the customer database. This correspondence is what allows generator-side
energy to be compared against customer-side billing at neighbourhood level.

Distance matters: the further a feeder runs, the higher its resistance and
the greater its technical loss at the same load.
