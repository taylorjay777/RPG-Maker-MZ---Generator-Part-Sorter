# RPG-Maker-MZ---Generator-Part-Sorter
Python script with GUI to help sort RPG Maker MZ Generator Folder (in Alpha Testing)

As I'm sure is the case for everyone else's generator folder, my generator folder is a *mess*. Stray unmatched sheets everywhere. I've been working on building this app to help me sort through my generator folder and would love to get some feedback from others on any bugs people might encounter, or any features people think would be helpful (will consider ones within reason/capability while remembering I am not a programmer and not intending at this point to make this into a big crazy thing). Right now it's just a python file, I am not at the state of packaging yet, so you should feel at least vaguely comfortable running a python script from the command line/terminal.



1) Please make a backup / copy of your Generator folder to test this on - I AM NOT RESPONSIBLE FOR DAMAGE TO YOUR GENERATOR FOLDER IF YOU DO NOT HEED THIS WARNING. This app is still very much in Alpha and can definitely make mistakes.

2) Python should be installed on your computer. You'll also need to install 2 libraries that this needs to run (will depend on which version of python you're running if you need to use python or python3:

python -m pip install Pillow PySide6
OR
python3 -m pip install Pillow PySide6

Pillow is an imaging library for Python that adds image processing capabilities to your Python interpreter
PySide6 is Python bindings for the Qt cross-platform application and UI framework

3) Run python generator_sorter.py to start the app (may need to CD down to wherever you saved the file).

4) You should be able to navigate to your generator folder (select the top level) and it will load in a interface similar to this that will allow you to review your parts as it loads the components from each folder. Clicking ok or next will move to the next item. Sort-> copy to sort folder should copy the relevant items (the ones displayed) to a newly created Sort folder (in your generator folder) Move will move the files from your generator folder to the sort folder (that way you can go through them later and resolve issues/fix items) and should also create a manifest of items moved. If a part has multiple images (ie clothing1 and clothing2, or face images with multiple components, it will load them into the dropdown and you should be able to look at all of them by changing the dropdown. 


So, yeah! If you're willing to try this out and let me know what issues you run into, it would be much appreciated! 
