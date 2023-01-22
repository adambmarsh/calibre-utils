import argparse
import os
import re
from subprocess import PIPE, run
from collections import namedtuple
from pynotifier import Notification  # NOQA
# from shlex import split

book_entry = namedtuple("book_entry", "id title author")

HOME_DIR = os.path.expanduser("~")


class CalibreHandler(object):

    def __init__(self, watched_dir="~/temp"):
        self._watched_dir = None

        self.watched_dir = watched_dir

        self._books = None
        self.books = self.get_all_db_books()

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
            return book_entry(-1, f"Unable to add book: received file {repr(in_file)}", None)

        b_id = int(result.stdout.split(wanted_str)[-1])

        return book_entry(b_id, "", None)

    @staticmethod
    def add_format(calibre_id="", in_file=""):
        """
        Add the named book format to Calibre

        :param calibre_id: The id of an existing book to which to add a new format
        :param in_file: The name of the file containing the book in the format to add
        :return: A book_entry tuple with the added book Calibre id on success or id set to -1 and book title to an
        error message on failure
        """
        command = ['/usr/bin/calibredb', 'add_format', str(calibre_id), in_file]
        result = run(command, stdout=PIPE, stderr=PIPE, universal_newlines=True)

        if result.returncode != 0:
            return book_entry(-1, f"Unable to add format: received file {in_file}", None)

        os.remove(in_file)
        return book_entry(calibre_id, "", None)

    @staticmethod
    def search_db(in_str=""):
        command = ['/usr/bin/calibredb', 'search', in_str]
        result = run(command, stdout=PIPE, stderr=PIPE, universal_newlines=True)
        print(result.returncode, result.stdout, result.stderr)
        # print(call_output)

        return result

    def convert_book(self, org_book="", dest_format="mobi"):
        command = ['/usr/bin/ebook-convert',
                   os.path.abspath(os.path.join(self.watched_dir, org_book)),
                   os.path.abspath(os.path.join(HOME_DIR, "temp", re.sub(r'epub$', dest_format, org_book)))]
        result = run(command, stdout=PIPE, stderr=PIPE, universal_newlines=True)

        wanted_str = "Output saved to "
        converted_res = next(iter([out_line for out_line in result.stdout.split("\n") if wanted_str in out_line]), "")

        return re.sub(re.compile(wanted_str), "", converted_res).strip() or ""

    @staticmethod
    def assemble_entries(in_entries=None):
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
        entry_model = {
            'id': '',
            'title': '',
            'author': ''
        }
        for ix, w_ent in enumerate(work_entries):
            re_match = re.search(r'^[0-9]+', w_ent)
            if re_match:
                ent = dict(entry_model)
                ent['id'] = w_ent[:re_match.end()].strip()
                ent_rest = w_ent[re_match.end():].strip()
                ent['author'] = re.split(r' {2,}', ent_rest)[-1]
                ent['title'] = next(iter(ent_rest), "")
                entries.append(ent)
                continue

            if ix < 1:
                continue

            if entries[ix - 1]:
                entries[ix - 1]['title'] = re.sub(r' +', ' ', " ".join([entries[ix - 1]['title'], w_ent.strip()]))

        return ["  ".join([v for v in ent.values()]) for ent in entries]

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
        for w_ent in work_entries:
            m = re.search(r'^[0-9]+ +', w_ent)

            if not m:
                continue

            part_a = w_ent[: m.end()].strip()
            w_ent = w_ent[m.end():]

            ent_parts = re.split(r'  +', w_ent)
            ent_parts = [part_a] + ent_parts

            if len(ent_parts) < 3 and re.search(r'[A-Za-z0-9]+$', w_ent):
                ent_parts.append(ent_parts[-1])
                ent_parts[-2] = ""

            book = dict(zip(keys, ent_parts))

            if not book:
                continue

            if book.get('id', None):
                entries.append(book)
                b_ix += 1
                continue

            if b_ix == 0:
                continue

            join_char = "" if entries[b_ix - 1]['title'].endswith('-') else " "
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

        # if author_res:
        #     work_str = re.sub(r'^[ \-_]+', '', working_title[working_title.rfind(splitter_str):]).strip()

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
            pat = re.compile(f"([\b]{part}[\b]|{part}[,. ])")
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

    @staticmethod
    def get_file_base_name_and_extension(file_name=""):
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

    def process_book(self, in_file=""):
        summary = "calibre-utils"
        abs_file_path = os.path.abspath(os.path.join(self.watched_dir, in_file))

        if not os.path.exists(abs_file_path):
            self._post_notification(summary, f"The file {repr(in_file)} does not exist.")
            return 0

        self._post_notification(summary, f"inotify_calibre: Processing  file {repr(in_file)} ...")

        file_base_name, extension_str = self.get_file_base_name_and_extension(file_name=in_file)

        if not extension_str or extension_str == file_base_name:
            self._post_notification(summary, f"Received file {repr(in_file)}, cannot process a file without extension.")
            return 0

        title = self.extract_title(file_base_name)

        if not title:
            self._post_notification(
                summary,
                f"Unable to extract book title from the received file name {repr(in_file)}, exiting.")
            return 0

        list_entry = self.matching_book(title)

        if list_entry.id == -1:
            self._post_notification(summary, in_file)
            return 0

        # If book not in DB, add it:
        if not list_entry.id:
            res_entry = self.add_book(abs_file_path)

            if res_entry.id == -1:
                self._post_notification(summary, in_file)
                return 0

            list_entry = book_entry(id=res_entry.id, title=title, author="")

        # Try converting the book (to mobi by default):
        convert_res = self.convert_book(org_book=in_file, dest_format="mobi" if extension_str == "epub" else "")

        if not convert_res:
            self._post_notification(
                summary,
                f"Unable to convert the book in file name {repr(in_file)} to mobi, exiting.")
            return 0

        # Add the new format to the book in Calibre:
        res_entry = self.add_format(list_entry.id, convert_res)

        processed_path = re.sub(r'in-books', 'processed', self.watched_dir)

        if res_entry.id > 0:
            self._post_notification(
                summary,
                f"{repr(in_file)} is in Calibre and converted to mobi, moving it to {processed_path}")

        # Save original file:
        os.rename(abs_file_path, os.path.abspath(os.path.join(processed_path, in_file)))

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

    ch = CalibreHandler(watched_dir=args.watched_dir)
    res = ch.process_book(in_file=args.in_file)

    if res > 0:
        exit(0)

    exit(res)
