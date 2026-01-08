import turtle as t
import math
#22ishaq - Github

screen = t.Screen()

# creating the traffic light head
head = t.Turtle()
head.hideturtle()
head.speed(0)
head.penup()
head.goto(-30, 135)
head.pendown()
head.fillcolor("black")
head.begin_fill()
for loop in range(2):
    head.forward(60)
    head.right(90)
    head.forward(180)
    head.right(90)
head.end_fill()

# creating the 3 lights
green_light = t.Turtle()
amber_light = t.Turtle()
red_light = t.Turtle()

for light in (green_light, amber_light, red_light):
    light.shapesize(1.5)
    light.shape("circle")
    light.penup()

# position the lights
green_light.goto(0, 100)
amber_light.goto(0, 50)
red_light.goto(0, 0)

# set inital light colours
green_light.color("green")
amber_light.color("gray")
red_light.color("gray")

# set inital states
state = 0
loop_state = False  

def lights_sequence():
    global state, loop_state
    #inital state
    if state == 0:  
        green_light.color("green")
        amber_light.color("gray")
        red_light.color("gray")
        delay = int(7000)

    #amber (3 seconds)
    elif state == 1:  
        green_light.color("gray")
        amber_light.color("orange")
        red_light.color("gray")
        delay = int(6000)

    #red (30 seconds)
    elif state == 2:  
        green_light.color("gray")
        amber_light.color("gray")
        red_light.color("red")
        delay = int(30000)

    #amber (3 seconds)
    elif state == 3:  
        green_light.color("gray")
        amber_light.color("orange")
        red_light.color("gray")
        delay = int(6000)

    #green (infinite)   
    elif state == 4:  
        green_light.color("green")
        amber_light.color("gray")
        red_light.color("gray")
        delay = int(1000000000)  
    
    state = (state + 1) % 5 
    screen.ontimer(lights_sequence, delay)


def start_cycle():
    global loop_state
    loop_state = True
    lights_sequence()

# start button 
button = t.Turtle()
button.shape("circle")
button.shapesize(3)
button.color("black")
button.penup()
button.goto(0, -150)

def on_click(x, y):
    if button.xcor() - 50 < x < button.xcor() + 50 and button.ycor() - 20 < y < button.ycor() + 20:
        start_cycle()

screen.onc
