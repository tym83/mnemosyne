reset('etching')
ground(30, material='plaster')
for y in (0, 9, 18):
    for x in (-9, 9):
        box(x-1.2, y-1.2, 0, x+1.2, y+1.2, 14, 'stone')
        cornice((x-1.5,y-1.5),(x-1.5,y+1.5),13,depth=.5)
    vault(-9,y-1,9,y+1,14,9,.8)
for x in (-10.5,10.5):
    box(x-.8,-2,0,x+.8,21,3,'stone')
stair(-8,4,0,13,7,3,24,direction=90)
box(-8,17,6.5,9,20,7,'stone')
vault(-8,17,9,20,7,3,.6)
figure(4,-3,scale=3)
figure(2,7,pose='walk')
camera((36,-48,29),(0,8,9),ortho_scale=51)
sun(azimuth=145,elevation=24,strength=4)
world(.16)
