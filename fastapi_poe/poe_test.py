import poe
 
# AI Model
# - GPT-4: beaver
# - ChatGPT: chinchilla
# - Claude+: a2_2
 
client = poe.Client(input("Enter The Token: "))
message = input("\n\tYou: ")
while message != "":
    print("\n\tBot: \n")
    for chunk in client.send_message("chinchilla", message):
        print(chunk["text_new"], end="", flush=True)
    message = input("\n\tYou: ")