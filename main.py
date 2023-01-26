import argparse
import os
import re
from collections import namedtuple
from enum import auto, Enum
from subprocess import PIPE, run
from pynotifier import Notification  # NOQA


book_entry = namedtuple("book_entry", "id title author")


HOME_DIR = os.path.expanduser("~")


class Result(Enum):
    PROCESSING = auto()
    FILE_DOES_NOT_EXIST = auto()
    NO_EXTENSION = auto()
    CANNOT_EXTRACT_TITLE = auto()
    TITLE_EMPTY = auto()
    BOOK_NOT_FOUND = auto()
    UNABLE_TO_ADD_BOOK = auto()
    CONVERSION_FAILED = auto()
    FORMAT_IN_DB = auto()
    UNABLE_TO_ADD_FORMAT = auto()
    PROCESSED = auto()


class CalibreBookHandler(object):
    """
    This class is dedicated to processing one book file at a time.
    Processing involves picking up the file from the designated directory,
    checking if it is in Calibre DB and if not adding it to Calibre and
    then converting it to mobi if the mobi format is not already in the DB.
    """
    def __init__(self, watched_dir="~/temp", book_file=""):
        self._book = None

        self.book_file = book_file

        self._watched_dir = None

        self.watched_dir = watched_dir

        self._processed_path = None
        self.processed_path = re.sub(r'in-books', 'processed', self.watched_dir)

        self._books = None
        self.books = self.get_all_db_books()

        self._abs_path = None
        self.abs_path = os.path.abspath(os.path.join(self.watched_dir, self.book_file))

    @property
    def book_file(self):
        return self._book_file

    @book_file.setter
    def book_file(self, in_book):
        self._book_file = in_book

    @property
    def abs_path(self):
        return self._abs_path

    @abs_path.setter
    def abs_path(self, in_path):
        self._abs_path = in_path

    @property
    def processed_path(self):
        return self._processed_path

    @processed_path.setter
    def processed_path(self, in_path):
        self._processed_path = in_path

    @property
    def books(self):
        return self._books

    @books.setter
    def books(self, in_books):
        self._books = in_books

    @property
    def watched_dir(self):
        return self._watched_dir

    @watched_dir.setter
    def watched_dir(self, in_dir):
        self._watched_dir = in_dir

    @staticmethod
    def add_book(in_file=""):
        """
        Add the named book to Calibre
        :param in_file: The name of the file containing the book to add
        :return: A book_entry tuple with the added book Calibre id on success or id set to -1 and book title to an
        error message on failure
        """
        command = ['/usr/bin/calibredb', 'add', in_file]
        result = run(command, stdout=PIPE, stderr=PIPE, universal_newlines=True)

        # print(repr(result))

        wanted_str = "Added book ids: "

        if wanted_str not in result.stdout:
            return book_entry(-1, Result.UNABLE_TO_ADD_BOOK, None)

        b_id = int(result.stdout.split(wanted_str)[-1])

        return book_entry(b_id, Result.PROCESSED, None)

    @staticmethod
    def get_book_formats(book_id, book_title=""):
        """
        Retrieve a list of formats in the Calibre DB for the given book title

        :param book_id: A string containing the identifier of the book for which to get existing formats
        :param book_title: The name of the file containing the book in the format to add
        :return: A book_entry tuple with the added book Calibre id on success or id set to -1 and book title to an
        error message on failure
        """
        command_all = ['/usr/bin/calibredb', 'list', '-s', book_title, "-f", "formats"]
        result_raw = run(command_all, stdout=PIPE, stderr=PIPE, universal_newlines=True)

        matched_book = ""

        for book_line in result_raw.stdout.split("\n"):
            if re.search(r'^(Fail|id +title|id +formats)', book_line):
                continue

            line_id = next(iter(re.findall(r'^\d+ +', book_line)), "").strip()

            if not line_id and not matched_book:
                continue

            if line_id and book_id.strip() != line_id:
                continue

            matched_book += book_line[0 if not line_id else len(line_id):]

            if "]" not in matched_book:
                continue

        return [re.sub(r'^\.', '', fmt) for fmt in re.findall(r'\.[a-z]+\b', matched_book)]

    @staticmethod
    def add_format(calibre_id="", in_file=""):
        """
        Add the named book format to Calibre

        :param calibre_id: The id of an existing book to which to add a new format
        :param in_file: The name of the file containing the book in the format to add or Result.FORMAT_IN_DB if the
        desired format is already present
        :return: A book_entry tuple with the added book Calibre id on success or id set to -1 and book title to an
        error message on failure
        """
        if in_file == Result.FORMAT_IN_DB:
            return book_entry(calibre_id, Result.FORMAT_IN_DB, None)

        command = ['/usr/bin/calibredb', 'add_format', str(calibre_id), in_file]
        result = run(command, stdout=PIPE, stderr=PIPE, universal_newlines=True)

        if result.returncode != 0:
            return book_entry(-1, Result.UNABLE_TO_ADD_FORMAT, None)

        os.remove(in_file)
        return book_entry(calibre_id, Result.PROCESSED, None)

    @staticmethod
    def search_db(in_str=""):
        command = ['/usr/bin/calibredb', 'search', in_str]
        result = run(command, stdout=PIPE, stderr=PIPE, universal_newlines=True)
        print(result.returncode, result.stdout, result.stderr)
        # print(call_output)

        return result

    def convert_book(self, org_book="", dest_format="mobi", existing_formats=None):
        """
        Convert given book to another format
        :param org_book: A string containing the name of the book file to convert; if not provided, use the instance
        member `book_file`
        :param dest_format: A string containing the name of the target format
        :param existing_formats: A list of existing book formats
        :return: On success, the name of the converted book file (with the target extension), otherwise
        an error code from the Result class
        """
        org_book = self.book_file or org_book
        existing_formats = list() if not existing_formats else existing_formats

        if dest_format in existing_formats:
            return Result.FORMAT_IN_DB

        command = ['/usr/bin/ebook-convert',
                   os.path.abspath(os.path.join(self.watched_dir, org_book)),
                   os.path.abspath(os.path.join(HOME_DIR, "temp", re.sub(r'epub$', dest_format, org_book)))]
        result = run(command, stdout=PIPE, stderr=PIPE, universal_newlines=True)

        wanted_str = "Output saved to "
        converted_res = next(iter([out_line for out_line in result.stdout.split("\n") if wanted_str in out_line]), "")

        return re.sub(re.compile(wanted_str), "", converted_res).strip() or Result.CONVERSION_FAILED

    def matching_book(self, title=""):
        default_ret = book_entry(id=-1, title="", author="")

        if not title:
            return default_ret

        for book in self.books:
            if title in re.sub(r':', '', book.get('title', '')):
                return book_entry(id=int(book.get('id', '')),
                                  title=book.get('title', ''),
                                  author=book.get('author', ''))

        return book_entry(id=0, title=title, author="")

    @staticmethod
    def db_entries_to_dict(in_entries=None):
        """

        :param in_entries: A list of strings representing entries in the DB: id, title, author
        :return: A list of dictionaries (id, title, author) that match `search_str`
        """
        if not in_entries:
            return list()

        work_entries = [ent for ent in in_entries if ent and not re.search(r'^(Fail|id +title)', ent)]

        if not work_entries:
            return in_entries

        entries = list()
        keys = ['id', 'title', 'author']

        b_ix = 0
        for w_entry in work_entries:
            id_str = next(iter(re.findall(r'^\d+ +', w_entry)), "")

            if id_str:
                w_entry = w_entry[len(id_str):]

            entry_parts = re.split(r'  +', w_entry)
            entry_parts = [id_str.strip()] + entry_parts if id_str else entry_parts

            if len(entry_parts) < 3 and re.search(r'[\w;,&]+$', w_entry):
                entry_parts.append(entry_parts[-1])
                entry_parts[-2] = ""

            book = dict(zip(keys, entry_parts))

            if not book:
                continue

            if book.get('id', None):
                entries.append(book)
                b_ix += 1
                continue

            if b_ix == 0:
                continue

            join_char = "" if re.search(r'[-/]+$', entries[b_ix - 1]['title']) else " "
            entries[b_ix - 1]['title'] += (join_char + book['title'])

            if book.get('author', ''):
                entries[b_ix - 1]['author'] = " ".join([entries[b_ix - 1]['author'], book['author']])

        return entries

    @staticmethod
    def remove_series_from_title(work_title=""):
        if not work_title:
            return ""

        rx_pattern = re.compile('[\[(][a-zA-Z0-9 -]+[\])]')  # NOQA
        if not re.search(rx_pattern, work_title):
            return work_title

        return re.sub(rx_pattern, '', work_title).strip()

    def get_all_db_books(self):
        command_all = ['/usr/bin/calibredb', 'list']
        result_all = run(command_all, stdout=PIPE, stderr=PIPE, universal_newlines=True)

        return self.db_entries_to_dict(result_all.stdout.split("\n"))

    def extract_title_if_hyphen(self, working_title=""):
        if " - " not in working_title:
            return working_title

        splitter_str = " - "

        work_str = working_title[: working_title.rfind(splitter_str)].strip()

        db_titles = [dbe.get('title', '') for dbe in self.books]
        title_res = [dbt for dbt in db_titles if work_str in dbt]

        if title_res:
            return work_str

        def is_subset(in_a, in_b):
            set_a = set(re.split(r'[. ,]+', in_a))
            set_b = set(re.split(r'[. ,]+', in_b))

            return set_a.issubset(set_b) or set_b.issubset(set_a)

        db_authors = list(set([dbe.get('author', '') for dbe in self.books]))
        author_res = [dba for dba in db_authors if work_str in dba or is_subset(work_str, dba)]

        if not author_res and splitter_str in work_str:
            return self.extract_title_if_hyphen(work_str)

        if not author_res and ", " in work_str:
            work_str = " ".join(work_str.split(", ")[::-1])
            author_res = [dba for dba in db_authors if work_str in dba]

        return self.remove_author(working_title, author_res)

    @staticmethod
    def remove_author(in_work_str, in_author=None):
        if not in_author:
            return in_work_str

        author = in_author

        if isinstance(in_author, list):
            author = " ".join(in_author)

        author_parts = re.split(r'[. ,]+', author)

        out_str = in_work_str

        for part in author_parts:
            pat = re.compile(f"({part}|{part}[,. ])")
            out_str = re.sub(pat, '', in_work_str)
            in_work_str = out_str

        return out_str.strip("- ")

    def extract_title(self, working_title=""):
        """
        Parse the received string to extract the title of the book (may be incomplete).
        Expect the title to be the first part, which  may be followed by " - " , followed by {author},m
        or " by {author}" or "({author})", and optionally, e.g. by " (z-library ...)"
        :param working_title: A string from which to extract the name of the book
        :return: The title of the book on success or an empty string on failure
        """
        working_title = self.remove_series_from_title(working_title)

        if not working_title:
            return ""

        zlib_str = "z-lib"
        pat = re.compile(r'[(]?' + zlib_str + r'(.org)?' + r'[)]?')
        working_title = re.sub(pat, "", working_title).strip()
        working_title = re.sub(r'[(.]+$', '', working_title)

        if " by " in working_title:
            splitter_str = " by "
            return working_title[: working_title.rfind(splitter_str)].strip()

        working_title = self.extract_title_if_hyphen(working_title)

        if re.search(r'[(].*[)] *$', working_title):
            return re.sub(r'[(].*[)] *$', "", working_title).strip()

        return working_title.strip()

    def get_file_base_name_and_extension(self, file_name=""):
        file_name = file_name or self.book_file

        matched = re.search(r'\.[a-zA-Z0-9]+$', file_name)

        if matched:
            return file_name[:matched.start()], file_name[matched.start()+1:matched.end()]

        return file_name, file_name

    @staticmethod
    def _post_notification(in_summary="calibre_utils", in_description=""):
        Notification(
            title=in_summary,
            description=in_description,
            icon_path='',  # On Windows .ico is required, on Linux - .png
            duration=5,  # Duration in seconds
            urgency='normal'
        ).send()

    def _notify(self, code):
        summary = "calibre-utils"

        notify_text = {
            Result.PROCESSING: f"inotify_calibre: Processing  file {repr(self.book_file)} ...",
            Result.FILE_DOES_NOT_EXIST: f"The file {repr(self.book_file)} does not exist.",
            Result.NO_EXTENSION: f"Received file {repr(self.book_file)}, cannot process a file without extension.",
            Result.CANNOT_EXTRACT_TITLE:
                f"Unable to extract book title from the received file name {repr(self.book_file)}, exiting.",
            Result.TITLE_EMPTY: f"Book title not found in file  {repr(self.book_file)}, exiting.",
            Result.UNABLE_TO_ADD_BOOK: f"Unable to add book: received file {repr(self.book_file)}",
            Result.CONVERSION_FAILED: f"Unable to convert {repr(self.book_file)} to mobi, exiting.",
            Result.FORMAT_IN_DB: f"{repr(self.book_file)} is in Calibre in mobi, moving it to {self.processed_path}",
            Result.UNABLE_TO_ADD_FORMAT: f"Unable to add format: received file {self.book_file}",
            Result.PROCESSED:
                f"{repr(self.book_file)} is in Calibre and converted to mobi, moving it to {self.processed_path}",
        }

        if code not in notify_text:
            return

        self._post_notification(summary, notify_text[code])

    def process_book(self):
        if not os.path.exists(self.abs_path):
            self._notify(Result.FILE_DOES_NOT_EXIST)
            return 0

        self._notify(Result.PROCESSING)

        file_base_name, extension_str = self.get_file_base_name_and_extension()

        if not extension_str or extension_str == file_base_name:
            self._notify(Result.NO_EXTENSION)
            return 0

        title = self.extract_title(file_base_name)

        if not title:
            self._notify(Result.CANNOT_EXTRACT_TITLE)
            return 0

        list_entry = self.matching_book(title)

        if list_entry.id == -1:
            self._notify(Result.TITLE_EMPTY)
            return 0

        # If book not in DB, add it:
        if not list_entry.id:
            res_entry = self.add_book(self.abs_path)

            if res_entry.id == -1:
                self._notify(Result.UNABLE_TO_ADD_BOOK)
                return 0

            list_entry = book_entry(id=res_entry.id, title=title, author="")

        # Try converting the book (to mobi by default):
        target_format = "mobi"
        convert_res = self.convert_book(dest_format=target_format if extension_str == "epub" else "",
                                        existing_formats=self.get_book_formats(str(list_entry.id), title))

        self._notify(convert_res)

        # Save original file:
        os.rename(self.abs_path, os.path.abspath(os.path.join(self.processed_path, self.book_file)))

        if convert_res in [Result.FORMAT_IN_DB, Result.CONVERSION_FAILED]:
            return 0

        # Add the new format to the book in Calibre:
        res_entry = self.add_format(list_entry.id, convert_res)

        self._notify(res_entry.title)

        return res_entry.id


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description="This program processes files added to a directory watched by "
                                                 "inotify, adding the input file(s) to Calibre and, if necessary, "
                                                 "converting  them to .mobi, then adding the .mobi format to Calibre "
                                                 "as well. ")
    parser.add_argument("-d", "--directory", help="Full path to the watched directory.",
                        type=str,
                        dest='watched_dir',
                        default='/home/adam/Downloads/books/in-books',
                        required=False)
    parser.add_argument("-f", "--file", help="The name of the file added to the watched directory.",
                        type=str,
                        dest='in_file',
                        required=False)

    args = parser.parse_args()

    if not args.in_file:
        exit(1)

    ch = CalibreBookHandler(watched_dir=args.watched_dir, book_file=args.in_file)
    res = ch.process_book()

    if res > 0:
        exit(0)

    exit(res)
