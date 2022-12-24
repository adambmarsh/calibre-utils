# caliber-utils #

This is a companion utility to [Calibre](https://calibre-ebook.com/). Its makes
adding books to Calibre and converting them to mobi (the Kindle-friendly format)
easy by allowing you to drop (copy) files containing epubs to a monitored folder
and then handling the conversion to mobi automatically. 

The utility consists of:

* inotify_calibre.sh -- a Bash script that uses inotify to monitor a folder for new epubs,
  or mobi files
* calibre-utils/main.py -- a Python script invoked by inotify_calibre.sh when
  one or more books have been put in the watched folder to check if the book is
  already in Calibre - if not, it adds the book -- and then converts it to mobi
  and adds the mobi format (this has no effect if a mobi version of the book is
  already in Calibre).

The Python script takes the following arguments:

* `-f` The name of the file to add to Calibre and convert (no path, just the name
  and extension)
* `-d` The absolute path to the directory to monitor (defaults to
  `$HOME/Downloads/books/in-books`

After processing each input file, the Python script moves it to
`$HOME/Downloads/books/processed`

The Python programs sends desktop notifications to the host system via
`pianotifier` (installed as `py-notifier`):

- on errors (if the input folder does not contain a file to process or an
  instance of Calibre is already running, the book cannot be added to Calibre,
  etc.)
- on success (a book has been added and converted or only converted if it was
  already present in Calibre) 

The monitoring process continues in the background until you kill the process
either directly or by restarting the computer.

Pre-requisites:
 - Calibre (e-book reader and db)
 - Python 3.10+
 - inotify-tools 3.22.6.0-1+
 - virtualenv (run "pip install virtualenv")
 
## Installation

1. Install the prerequisites -- see above
2. Clone the repository containing caliber-utils.
3. Install the dependencies as listed in requirements.txt in the virtual
   environment (in the cloned directory, run `pip install -r requirements.txt`)
4. Make inotify_calibre.sh executable (`chmod + {cloned_dir}/inotify_calibre.sh`) 
5. Create (if necessary) the directory for inotify to monitor
   (`$HOME/Downloads/books/in-books`) as well as the directory to which the
   utility is to copy the input files after processing
   (`$HOME/Downloads/books/processed`) 
6. Update variables in inotify_calibre.sh -- see below

### Set Variables in inotify_calibre.sh

Here are the variables to set, although the paths must be appropriate to your system:

* `activate_path="$HOME/.virtualenvs/calibre-utils/bin/activate"`
* `python_pkg="$HOME/scripts/calibre-utils/main.py"`
* `python_log="$HOME/Downloads/books/processed/inotify.log"`
* `default_incoming_books_dir="$HOME/Downloads/books/in-books"`

## Using caliber-utils

After installation, invoke the utility in a Bash terminal as follows:

    $ ~/{path_to_cloned_dir)/inotify_calibre.sh 


## Status

24 Dec 2022 First draft, tested locally and working

## Copyright

Copyright Adam Bukolt

Note that the copyright refers to the code and scripts in this repository and
expressly not to any third-party dependencies or the Calibre application.

## License

MIT

Note that separate licenses apply to third-party dependencies and the Calibre application.
