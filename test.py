user_input=int(input("Enter a number"))
x=user_input
fact=1
for i in range(user_input):
    fact=fact*x
    x-=1
print(fact)
