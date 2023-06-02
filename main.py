"""A simple use of `mccmdhl2.tkapp`.
Run this and a Minecraft Bedrock command "IDE" will start.
"""

import tkinter
from mccmdhl2.tkapp import MCCmdText

root = tkinter.Tk()
text = MCCmdText(root, font=("Courier", 16))
text.pack()
root.mainloop()
