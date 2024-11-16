#!/bin/bash

# me="${0##*/}"
# echo "$me called"

## Set paths as appropriate to your system:
activate_path="$HOME/.virtualenvs/calibre-utils/bin/activate"
python_pkg="$HOME/scripts/calibre-utils/main.py"
python_log="$HOME/Downloads/books/processed/inotify.log"
default_incoming_books_dir="$HOME/Downloads/books/in-books"

if [ -n "$1" ]; then
    target_dir="$1"
else
    target_dir="$default_incoming_books_dir"
fi

# inotifywait -m -e close_write $target_dir |
inotifywait -m -e moved_to "$target_dir" |
    while read -r dir op file;
    do         
        echo "dir=$dir op=$op file=$file"
        . "$activate_path" && python "$python_pkg" -d "$dir" -f """$file""" > "$python_log" && deactivate
    done &
