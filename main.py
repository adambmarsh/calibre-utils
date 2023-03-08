import argparse
import os
import re
from collections import namedtuple
from enum import auto, Enum
from subprocess import PIPE, run

import dbusnotify


book_entry = namedtuple("book_entry", "id title author error")


HOME_DIR = os.path.expanduser("~")


def log_it(level='info', src_name=None, text=None):
    import logging

    logging.basicConfig(level=logging.DEBUG)
    logger_name = src_name if src_name else __name__
    log_writer = logging.getLogger(logger_name)

    if level == 'info':
        log_writer.info(text)
    elif level == 'error':
        log_writer.error(text)
    elif level == 'warning':
        log_writer.warning(text)
    else:
        log_writer.debug(text)


class Result(Enum):
    PROCESSING = auto()
    FILE_DOES_NOT_EXIST = auto()
    NO_EXTENSION = auto()
    CANNOT_EXTRACT_TITLE = auto()
    TITLE_EMPTY = auto()
    BOOK_NOT_FOUND = auto()
    UNABLE_TO_ADD_BOOK = auto()
    CONVERSION_FAILED = auto()
    CONVERSION_ABANDONED_PDF = auto()
    CONVERSION_SUCCESSFUL = auto()
    FORMAT_IN_DB = auto()
    UNABLE_TO_ADD_FORMAT = auto()
    PROCESSED = auto()
    UNKNOWN = auto()


class CalibreBookHandler(object):
    """
    This class is dedicated to processing one book file at a time.
    Processing involves picking up the file from the designated directory,
    checking if it is in Calibre DB and if not adding it to Calibre and
    then converting it to mobi if the mobi format is not already in the DB.
    """
    def __init__(self, watched_dir="~/temp", book_file=""):
        self._book = None

        self._watched_dir = None

        self.watched_dir = watched_dir

        self._processed_path = None
        self.processed_path = re.sub(r'in-books', 'processed', self.watched_dir)

        self._books = None
        self.books = self.get_all_db_books()

        self._abs_path = None
        self.book_file = self.abs_path = book_file

        # self.abs_path = os.path.abspath(os.path.join(self.watched_dir, self.book_file))

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
    def abs_path(self, in_file):
        self._abs_path = os.path.abspath(os.path.join(self.watched_dir, in_file))

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
        :return: A book_entry tuple with the added book Calibre id on success or id set to -1 and error to an
        error message on failure
        """
        command = ['/usr/bin/calibredb', 'add', in_file]
        result = run(command, stdout=PIPE, stderr=PIPE, universal_newlines=True)

        # log_it("debug", __name__, repr(result))

        wanted_str = "Added book ids: "

        if wanted_str not in result.stdout:
            return book_entry(-1, "", None, Result.UNABLE_TO_ADD_BOOK)

        b_id = int(result.stdout.split(wanted_str)[-1])

        return book_entry(b_id, "", None, Result.PROCESSED)

    @staticmethod
    def get_book_formats(book_id, book_title=""):
        """
        Retrieve a list of formats in the Calibre DB for the given book title

        :param book_id: A string containing the identifier of the book for which to get existing formats
        :param book_title: The name of the file containing the book in the format to add
        :return: A list of strings representing the book formats present in the DB
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
    def add_format(calibre_id="", in_file="", in_result=Result.PROCESSING):
        """
        Add the named book format to Calibre

        :param calibre_id: The id of an existing book to which to add a new format
        :param in_file: The name of the file containing the book in the format to add or Result.FORMAT_IN_DB if the
        desired format is already present
        :param in_result: The result of the last operation (a member of Result class)
        :return: A book_entry tuple with the added book Calibre id on success or id set to -1 and error to an
        error message on failure
        """
        if in_result == Result.FORMAT_IN_DB:
            return book_entry(calibre_id, "", None, Result.FORMAT_IN_DB)

        command = ['/usr/bin/calibredb', 'add_format', str(calibre_id), in_file.strip()]
        result = run(command, stdout=PIPE, stderr=PIPE, universal_newlines=True)

        if result.returncode != 0:
            return book_entry(-1, "", None, Result.UNABLE_TO_ADD_FORMAT)

        os.remove(in_file)
        return book_entry(calibre_id, "", None, Result.PROCESSED)

    @staticmethod
    def search_db(in_str=""):
        command = ['/usr/bin/calibredb', 'search', in_str]
        result = run(command, stdout=PIPE, stderr=PIPE, universal_newlines=True)

        log_it(level="info", text=f"{result.returncode}, {result.stdout}, {result.stderr}")

        return result

    def convert_book(self, org_book="", dest_format="mobi", existing_formats=None):
        """
        Convert given book to another format
        :param org_book: A string containing the name of the book file to convert; if not provided, use the instance
        member `book_file`
        :param dest_format: A string containing the name of the target format
        :param existing_formats: A list of existing book formats
        :return: On success, Result.CONVERSION_SUCCESSFUL and path to conversion output, otherwise
        an error code from the Result class and conversion output ("")
        """
        org_book = self.book_file or org_book
        existing_formats = list() if not existing_formats else existing_formats

        if org_book.endswith("pdf"):
            return Result.CONVERSION_ABANDONED_PDF, ""

        if dest_format in existing_formats:
            return Result.FORMAT_IN_DB, ""

        command = ['/usr/bin/ebook-convert',
                   os.path.abspath(os.path.join(self.watched_dir, org_book)),
                   os.path.abspath(os.path.join(HOME_DIR, "temp", re.sub(r'epub$', dest_format, org_book)))]
        result = run(command, stdout=PIPE, stderr=PIPE, universal_newlines=True)

        wanted_str = "Output saved to "
        conversion_output = next(iter([out_line for out_line in result.stdout.split("\n") if wanted_str in out_line]),
                                 "")

        return (Result.CONVERSION_SUCCESSFUL, conversion_output[len(wanted_str):].strip()) if conversion_output else \
            (Result.CONVERSION_FAILED, "")

    def matching_book(self, info=None):
        default_ret = book_entry(id=-1, title="", author="", error="")

        if not info.title:
            return default_ret

        def test_title_author_sets(in_db_book, in_book):
            db_title = re.sub(r'[:_-]+', '', in_db_book.get('title', ''))
            title_set = set(re.split(r' +', re.sub(r'[:_-]+', '', in_book.title)))
            db_title_set = set(re.split(r' +', db_title))
            db_author_set = set(re.split(r'[ .]+', in_db_book.get('author', "")))
            in_author_set = set(re.split(r'[ .]+', in_book.author))

            if in_book.title in db_title:
                return True

            if not (title_set.issubset(db_title_set) or db_title_set.issubset(title_set)):
                return False

            if not in_author_set or not in_book.author:
                return True

            return db_author_set.issubset(title_set) or db_author_set.issubset(in_author_set)

        for book in self.books:
            if test_title_author_sets(book, info):
                return book_entry(id=int(book.get('id', '')),
                                  title=book.get('title', ''),
                                  author=book.get('author', ''),
                                  error=Result.PROCESSING)

        return book_entry(id=0, title=info.title, author=info.author, error=Result.BOOK_NOT_FOUND)

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

    def remove_series_from_title(self, work_title=""):
        if not work_title:
            return "", ""

        rx_pattern = re.compile('[\[(][a-zA-Z0-9 -]+[\])]')  # NOQA

        matches = re.finditer(rx_pattern, work_title)
        if not matches:
            return work_title, ""

        poss_titles = poss_authors = list()
        for mt in matches:
            found_str = work_title[mt.start():mt.end()].strip("()[]")
            poss_titles = [dbb for dbb in self.books if self.is_subset(found_str, dbb.get('title', ''))]
            poss_authors = [dbb for dbb in self.books if self.is_subset(found_str, dbb.get('author', ''))]

        if not poss_titles and not poss_authors:
            return re.sub(rx_pattern, '', work_title).strip(), ""

        if poss_authors:
            possible = next(iter(poss_authors), {})
            author = possible.get('author', "")
            return re.sub(rx_pattern, '', work_title).strip(), author

        return work_title, ""

    def get_all_db_books(self):
        command_all = ['/usr/bin/calibredb', 'list']
        result_all = run(command_all, stdout=PIPE, stderr=PIPE, universal_newlines=True)

        return self.db_entries_to_dict(result_all.stdout.split("\n"))

    @staticmethod
    def is_subset(in_a, in_b):
        set_a = set(re.split(r'[:_. ,]+', in_a))
        set_b = set(re.split(r'[:_. ,]+', in_b))

        return set_a.issubset(set_b) or set_b.issubset(set_a)

    def is_name(self, in_str):
        """
        Check if the supplied string is part of an author's name in the DB
        :param in_str: String to check
        :return: True on success or False if no match
        """
        for dbb in self.books:
            if self.is_subset(in_str, dbb.get("author", "")):
                return True

        return False

    def is_title(self, in_str):
        """
        Check if the supplied string is part of a title in the DB
        :param in_str: String to check
        :return: True on success or False if no match
        """
        for dbb in self.books:
            if self.is_subset(in_str, dbb.get("title", "")):
                return True

        return False

    def extract_title_if_hyphen(self, working_title=""):
        default_ret = book_entry(id=-1, title=working_title, author="", error=Result.TITLE_EMPTY)
        if " - " not in working_title:
            return default_ret

        splitter_str = " - "
        split_title = working_title.split(splitter_str, 1)
        before_split = next(iter(split_title), "").strip()
        after_split = split_title[1].strip("- ")

        # Swap work author and title values if work_author could be part of existing DB book title
        is_title_after = (self.is_title(after_split) or not self.is_name(after_split))
        work_author = before_split if is_title_after else after_split
        work_title = after_split if is_title_after else before_split

        db_poss_title = [dbb for dbb in self.books if self.is_subset(work_title, dbb.get("title", ""))]
        if db_poss_title:
            for db_bk in db_poss_title:
                db_author = db_bk.get("author", None)
                if self.is_subset(work_author, db_author) or self.is_subset(db_author, work_title):
                    return book_entry(
                        id=db_bk.get("id", ""),
                        title=db_bk.get("title", ""),
                        author=db_bk.get("author", None),
                        error=Result.PROCESSING
                    )

        db_poss_author = [dbb for dbb in self.books if self.is_subset(work_title, dbb.get("author", None))]
        for db_bk in db_poss_author:
            if self.is_subset(work_author, db_bk.get("title", None)):
                return book_entry(
                    id=db_bk.get("id", ""),
                    title=db_bk.get("title", ""),
                    author=db_bk.get("author", ""),
                    error=Result.PROCESSING
                )

        return book_entry(id=-1, title=work_title or working_title, author=work_author, error=Result.PROCESSING)

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

    def extract_title_author(self, working_title=""):
        """
        Parse the received string to extract the title of the book (may be incomplete).
        Expect the title to be the first part, which  may be followed by " - " , followed by {author},m
        or " by {author}" or "({author})", and optionally, e.g. by " (z-library ...)"
        :param working_title: A string from which to extract the name of the book
        :return: A book_entry with the title of the book and error set to Result.Processing or an empty title and
        error set to Result.TITLE_EMPTY on failure
        """
        default_return = book_entry(id=-1, title="", author="", error=Result.TITLE_EMPTY)
        working_title, working_author = self.remove_series_from_title(working_title)

        if not working_title:
            return default_return

        zlib_str = "z-lib"
        pat = re.compile(r'[(]?' + zlib_str + r'(.org)?' + r'[)]?')
        working_title = re.sub(pat, "", working_title).strip()
        working_title = re.sub(r'[(.]+$', '', working_title)

        if " by " in working_title:
            splitter_str = " by "
            splitter_ix = working_title.rfind(splitter_str)
            return book_entry(id=-1,
                              title=working_title[: splitter_ix].strip(),
                              author=working_title[splitter_ix + len(splitter_str):].strip(),
                              error=Result.PROCESSING)

        working_info = self.extract_title_if_hyphen(working_title)
        working_title = working_info.title if working_info.title else working_title

        return book_entry(id=-1,
                          title=re.sub(r'[(].*[)] *$', "", working_title).strip(),
                          author=working_info.author or working_author,
                          error=Result.PROCESSING)

    def get_file_base_name_and_extension(self, file_name=""):
        file_name = file_name or self.book_file

        matched = re.search(r'\.[a-zA-Z0-9]+$', file_name)

        if matched:
            return file_name[:matched.start()], file_name[matched.start()+1:matched.end()]

        return file_name, file_name

    @staticmethod
    def _post_notification(in_summary="calibre_utils", in_description=""):
        icon_file = os.path.join(os.getcwd(), 'calibre-utils.png')
        dbusnotify.write(
            in_description,
            title=in_summary,
            icon=icon_file,  # On Windows .ico is required, on Linux - .png
        )

    def _notify(self, code=Result.UNKNOWN, alt_text=None):
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
            Result.CONVERSION_SUCCESSFUL: f"Converted {repr(self.book_file)} to mobi",
            Result.FORMAT_IN_DB: f"{repr(self.book_file)} is in Calibre in mobi, moving it to {self.processed_path}",
            Result.UNABLE_TO_ADD_FORMAT: f"Unable to add format: received file {self.book_file}",
            Result.PROCESSED:
                f"{repr(self.book_file)} is in Calibre and converted to mobi, moving it to {self.processed_path}",
            Result.CONVERSION_ABANDONED_PDF: f"{repr(self.book_file)} is a PDF file, please try manual conversion"
        }

        if alt_text:
            self._post_notification(summary, alt_text)
            return

        if code not in notify_text:
            return

        self._post_notification(summary, notify_text[code])

    def process_book(self, in_book=""):
        if in_book:
            self.book_file = in_book
            self.abs_path = in_book
        if not os.path.exists(self.abs_path):
            self._notify(code=Result.FILE_DOES_NOT_EXIST)
            return 0

        self._notify(Result.PROCESSING)

        file_base_name, extension_str = self.get_file_base_name_and_extension()

        if not extension_str or extension_str == file_base_name:
            self._notify(Result.NO_EXTENSION)
            return 0

        ex_info = self.extract_title_author(file_base_name)

        if not ex_info.title or ex_info.error != Result.PROCESSING:
            self._notify(Result.CANNOT_EXTRACT_TITLE)
            return 0

        list_entry = self.matching_book(ex_info)

        if list_entry.id == -1:
            self._notify(Result.TITLE_EMPTY)
            return 0

        # If book not in DB, add it:
        if not list_entry.id:
            res_entry = self.add_book(self.abs_path)

            if res_entry.id == -1:
                self._notify(Result.UNABLE_TO_ADD_BOOK)
                return 0

            list_entry = book_entry(id=res_entry.id, title=list_entry.title, author=list_entry.author, error="")

        # Try converting the book (to mobi by default):
        target_format = "mobi"
        convert_res, out_file = self.convert_book(
            dest_format=target_format,
            existing_formats=self.get_book_formats(str(list_entry.id), list_entry.title))

        self._notify(convert_res)

        # Save original file:
        os.rename(self.abs_path, os.path.abspath(os.path.join(self.processed_path, self.book_file)))

        if convert_res in [Result.FORMAT_IN_DB, Result.CONVERSION_FAILED, Result.CONVERSION_ABANDONED_PDF]:
            return 0

        # Add the new format to the book in Calibre:
        res_entry = self.add_format(list_entry.id, out_file)

        self._notify(res_entry.error)

        return res_entry.id

    def _relative_path(self, parent, children):
        return [os.path.join(parent, child) if parent != self.watched_dir else child for child in children]

    def list_dir_files(self, in_dir=None):
        if not in_dir:
            in_dir = self.watched_dir

        out_files = list()
        for curr_dir, sub_dirs, files in os.walk(in_dir):
            out_files += self._relative_path(curr_dir, files)
            # out_files += self._full_path(curr_dir, files) + [curr_dir] + self._full_path(curr_dir, sub_dirs)

        return out_files


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
                        default="",
                        required=False)

    args = parser.parse_args()

    ch = CalibreBookHandler(watched_dir=args.watched_dir, book_file=args.in_file)

    target_files = [args.in_file] if args.in_file else ch.list_dir_files()

    for count, file in enumerate(target_files):
        res = ch.process_book(file)

        log_it(level="info", text=f"Processed file {file}, {count+1}/{len(target_files)}, with result {res}")

    exit(0)
