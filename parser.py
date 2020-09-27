import re
import requests
import threading


def main():
    """
    main function
    """
    greeting = """Hello! To get information about teachers type 1. To get information about departments print 2. Type 0 to exit.
Rating about teachers was fetched from:
    1) vk.com/pmprepod and represented in format "positive-negative-neutral | total"
    2) professorrating.org, represented as number <= 5
so, 1 or 2?"""
    print(greeting)

    # cycle while not exit
    inp = ''
    while inp != '0':
        inp = input()
        if inp == '1':
            print_all_teachers_data()
        elif inp == '2':
            print_all_departments_data()


def print_all_teachers_data():
    """
    prints all data about teachers

    return:
        error

    errors:
        0 OK
        -1 something went wrong
    messages, if errors occur, are written from this function, so no need to handle them later
    """
    err, data = get_parsed_data('teachers')
    if err:
        last_level_error(msg='information about teachers')
        return -1

    # get teachers' rating
    teachers_data_dict = data
    teachers_names = sorted(teachers_data_dict)
    err, ratings = get_ratings_by_teachers_names(teachers_names)
    if err:
        last_level_error(msg="teachers' rating")
        return -1

    # first line in 2d list that will be printed, representing titles of columns
    labels = [('name', 'degree', 'department', 'rank', 'VK rating', 'professorrating.org')]

    # adding info about teacher to output list
    output_rows = labels + [
        (name,
         teachers_data_dict[name]['degree'],
         teachers_data_dict[name]['department'],
         teachers_data_dict[name]['rank'],
         *ratings[name],
         ) for name in teachers_names
    ]
    # print everything
    print_formatted(output_rows)


def print_all_departments_data():
    """
    prints data about departments

    return:
        err

    errors:
        0 OK
        -1 something went wrong
    error messages are print inside this function
    """
    err, departments_data = get_parsed_data('departments')
    if err:
        last_level_error('list of departments')
        return -1
    labels = [['department name']]
    dept_data = transpose([departments_data])
    # need to transpose to make Nx1 matrix (it is originally 1xN)

    output_data = labels + dept_data
    print_formatted(output_data)


def last_level_error(msg):
    """
    prints error which occurred in print_all_teachers_data() or print_all_departments_data()

    args:
        msg - message added to print
    """
    print(f'Was unable to get {msg}! Try to check connection and then repeat command')


def print_formatted(output_rows, separate_labels=True, delta=1):
    """
    given 2-dimensional list, outputs data, so that each element in column is placed directly under
    another(with no shifts to left or right caused by different lengths)

    args:
        output_rows - 2-dimensional list of any data that can be represented as string
        delta=1 - additional spaces added before and after every word in output
    """

    # find max length for each column
    lengths = [
        [len(str(elem)) for elem in output_row] for output_row in output_rows
    ]
    max_lengths = [max(column) for column in transpose(lengths)]

    # pattern to format strings, created from max length of corresponding columns
    pattern = ''.join([
        '{:^' + str(max_length + 2 * delta) + '}' for max_length in max_lengths
    ])

    # printing_formatted output
    print(pattern.format(*output_rows[0]))
    if separate_labels:
        print('\n')
    for output_row in output_rows[1:]:
        print(pattern.format(*output_row))


def transpose(matrix):
    """
    transpose 2d matrix.
    used in print_formatted() to get max number in each column

    args:
        matrix - 2d list
    """
    return list(zip(*matrix))


def get_ratings_by_teachers_names(teachers):
    """
    get compound rating from teachers' names. if rating for someone is not found, it will be represented by '---'

    args:
        teachers - list of teachers' names (or another object that acts like it when iterated, such as dict or set)

    return:
        err,
        rating_compound - dict of format: {
                <name>:(
                    <formatted rating from vk>,
                    <formatted rating from professorrating.org>
                )
            }

    errors:
        0 OK
        -1 something went wrong, operation is aborted, no intermediate values is returned
    """
    # creating threads to get different ratings
    ratings = {}
    threads = [
        threading.Thread(target=get_rating_wrapper, args=(mode, teachers, ratings))
        for mode in ('vk', 'prof_rat')
    ]
    [thread.start() for thread in threads]
    [thread.join() for thread in threads]

    # if ratings doesn't have 2 elements, then somewhere error occurred and operation has to be aborted
    if len(ratings) != 2:
        return (-1, 0)

    # if everything is ok, create returned dict
    rating_compound = {
        name: (
            rating_format(ratings['vk'][name], mode='vk') if name in ratings['vk'] else '---',
            rating_format(ratings['prof_rat'][name], mode='prof_rat') if name in ratings['prof_rat'] else '---',
        ) for name in teachers
    }
    return (0, rating_compound)


def get_parsed_data(mode):
    """
    get parsed data about teachers or department

    args:
        mode - 'teachers' or 'departments'(another causes exception)

    return:
        error,
        response - what got from corresponding to mode function

    errors:
        0 - OK
        -1 not ok
    """

    # initializing which url, function and file_name use for this mode
    if mode == 'teachers':
        url = 'http://www.apmath.spbu.ru/ru/staff/'
        parser_function = parse_teachers
    elif mode == 'departments':
        url = 'http://www.apmath.spbu.ru/ru/structure/depts/'
        parser_function = parse_departments
    else:
        raise WrongModeException('mode passed in get_parsed_data() is wrong!')

    err, response = try_getting_response(url)
    if not err:
        # getting parsed information from parser function
        html_text = response.text
        data_dict = parser_function(html_text)
        return (0, data_dict)

    # error happened
    return (-1, 0)


"""
functions to get rating
"""


def default_post_args_for_vk():
    """
    returns default argument for post request to vk API
    """
    return {
        'group_id': 42037,
        'access_token': '01a5cc4c01a5cc4c01a5cc4c5a01d1d56f001a501a5cc4c5ec869fd79e0861db86f6ec3',
        'v': '5.124',
    }


def get_meaning_of_opinion(word):
    """
    tries to find what does opinion-word mean\
    args:
        word to find meaning of
    return:
        meaning:
            'up' if positive
            'down' if negative
            'neutral' if neutral
            None - if can't figure out
    """

    word = word.lower()
    # try from standard options
    standard_words = {
        'положительное': 'up',
        'хорошо': 'up',
        'отрицательное': 'down',
        'плохо': 'down',
        'нейтральное': 'neutral',
    }
    if word in standard_words:
        return standard_words[word]

    # try by finding substring of word
    substrings = {
        'пол': 'up',
        'хор': 'up',
        'отр': 'down',
        'пло': 'down',
        'нейтр': 'neutral',
    }
    for substring in substrings:
        if substring in word:
            return substrings[substring]
    # could not find meaning
    return None


def get_rating_by_topic_id(topic_id):
    """
    tries to get teacher's rating from topic
    args:
        id of topic
    return:
        err,
        data about poll - dict{
                'total' - total votes, int
                'up' - percent of positives, float
                'down' - % of negatives, float
                'neutral' - % of neutral, float
            }
    errors:
        0 OK
        -1 could not get request
        1 topic doesn't have poll to get rating from
        2 could not understand information given in poll
    """

    default_args = default_post_args_for_vk()

    # merging default_args dict with dict of additional arguments
    post_args = {
        **default_args,
        **{
            'topic_id': topic_id,
            'count': 0,
        }
    }
    # getting data about topic
    error, board_data = try_getting_response('https://api.vk.com/method/', method='board.getComments',
                                             post_args=post_args)
    if error:
        return (-1, 0)

    # response is json. So board_data is now dict
    board_data = board_data.json()

    # if there's poll in topic
    if 'poll' not in board_data['response']:
        return (1, None)

    # getting data about votes
    total_votes = board_data['response']['poll']['votes']
    poll_answers = board_data['response']['poll']['answers']
    answers_distribution = {'up': 0, 'down': 0, 'neutral': 0}
    # getting meaning
    for poll_answer in poll_answers:
        poll_text_meaning = get_meaning_of_opinion(poll_answer['text'])

        # if understood meaning
        if poll_text_meaning:
            answers_distribution[poll_text_meaning] = poll_answer['rate']
        else:
            return (2, 0)
    return (0, {'total': total_votes, **answers_distribution})


def get_rating_by_topic_id_wrapper(topic_id, container, key):
    """
    wrapper to make threads possible for get_rating_by_topic_id()
    args:
        topic_id - will be passed to function,
        container - dict, to which returned values of function will be written,
        key - name for response in dict

    addition made to container: {
        <key>:<distribution>   #error is not written
    }

    <distribution> has such format: {
                                'total' - total votes, int
                                'up' - percent of positives, float
                                'down' - % of negatives, float
                                'neutral' - % of neutral, float
                            }
    """
    err, distribution = get_rating_by_topic_id(topic_id)
    if not err:
        container[key] = distribution


def get_topics_list():
    """
    get data about all topics in group
    return:
        err,
        topic_ids - dict of format <topic title>:<id>
    err:
        0 OK
        -1 error in request
    """
    default_args = default_post_args_for_vk()
    # dict merge
    post_args = {
        **default_args,
        **{
            'count': 0,
            'offset': 0,
        }
    }

    err, board_data = try_getting_response('https://api.vk.com/method', method='board.getTopics', post_args=post_args)
    if err:
        return (-1, 0)

    board_data = board_data.json()
    # board_data is dict made from json

    number_of_topics = board_data['response']['count']

    # dict of <title>:<id>
    topics_ids = {}

    # vk API allows only getting no more that 100 topics per 1 time. To get another 100, need to use offset
    # loop has ~ 2 iterations so threading is not really needed
    post_args['count'] = 100
    for offset in range(0, number_of_topics, 100):
        post_args['offset'] = offset
        err, board_data = try_getting_response('https://api.vk.com/method', method='board.getTopics',
                                               post_args=post_args)
        if err:
            return (-1, 0)
        board_data = board_data.json()
        # ..['items'] contains data about all of topics
        for topic in board_data['response']['items']:
            topics_ids[topic['title']] = topic['id']
    return (0, topics_ids)


def get_ratings_from_vk(teachers):
    """
    given teachers names returns rating from vk

    args:
        teachers - list of teachers' names (or another object that acts like it when iterated, such as dict or set)
    return:
        err,
        ratings - dict of format: {
                <teacher's name>:<distribution>,
                ...
            }

    <distribution> has such format: {
                                'total' - total votes
                                'up' - percent of positives
                                'down' - % of negatives
                                'neutral' - % of neutral
                            }

    errors:
        0 OK
        -1 not ok
    """
    ratings = {}
    err, topics_ids = get_topics_list()
    if not err:
        threads = []
        for name in teachers:
            if name in topics_ids:
                threads.append(
                    threading.Thread(target=get_rating_by_topic_id_wrapper, args=(topics_ids[name], ratings, name)))
        [thread.start() for thread in threads]
        [thread.join() for thread in threads]
        # if ratings is not empty:
        if ratings:
            return (0, ratings)

    # when some type of error happened

    return (-1, 0)


def professorrating_parse_by_page(page):
    """
    given page number returns parsed data about professors and their rating

    args:
        page - number of page to make post request

    return:
        err,
        names_ratings - list of format [
                            (<name of teacher>, <rating>),
                            ...
                        ]

    <rating> has a format of string, storing one float (e. g. "4.3")
    errors:
        0 OK
        -1 unable to get response
    """

    url = 'https://professorrating.org/blocks'
    post_args = {'page': page, 'id': 2445, 'typePR': 4}
    err, response = try_getting_response(url, method='page_helper.php', post_args=post_args)
    if err:
        return (-1, 0)

    text = response.text.replace('ё', 'е')  # because this letter doesn't match regex ('ё' > 'я')

    # returns list of 4*n+3, where n is num of names
    # +3 because last three are rubbish
    # each of n names is repeated 4 times in a row
    names_raw = re.findall(r'[а-яА-Я][а-яА-Я ]*', text)
    names = names_raw[:40][::4]

    # ratings of teachers is in the same order as in names
    ratings = re.findall(r'\d+\.\d+', text)
    return (0, zip(names, ratings))


def proffessorrating_parser_wrapper(page, rating_container):
    """
    wrapper to make threads possible for professorrating_parse_by_page()
    args:
        page - will be passed to function,
        rating_container - dict, to which returned values of function will be written,


    additions made to rating_container: {
        <name of teacher>:<corresponding rating>
        ...                              #error is not written
    }
    """
    err, names_ratings = professorrating_parse_by_page(page)
    if not err:
        for name, rating in names_ratings:
            # if rating is 0.0 then it is not stored
            if float(rating):
                rating_container[name] = rating


def get_total_num_of_professorrating_pages():
    """
    finds and returns total number of pages on site having data about rating

    return:
        err,
        num_of_pages <- int

    errors:
        0 OK
        1 could not get request, return default_num(214) as num_of_pages
    """
    default_num = 214

    # getting page on which info about pages is stored
    err, response = try_getting_response('https://professorrating.org/kafedra.php?id=2445#gsc.tab=0')
    if not err:
        html_text = response.text
        # line about number of pages has this format: (e.g. "1 по 10 из 214", where 214 is number we need)
        possible_number = re.search(r'\d+ по \d+ из (\d+)', html_text)
        if possible_number:
            return (0, int(possible_number[1]))
    print('unable to get number of pages from professorrating!')
    return (1, default_num)


def get_rating_from_professorrating(teachers):
    """
    given teachers names returns rating from professorrating.org

    args:
        teachers - list of teachers' names (or another object that acts like it when iterated, such as dict or set)
    return:
        err,
        rating - dict of format: {
                            <name>:<rating>
                        }

    errors:
        0 OK
        -1 not ok
    """

    # get total number of pages
    _, num_of_pages = get_total_num_of_professorrating_pages()

    # create thread for each page
    ratings = {}
    threads = []
    for page_num in range(0, num_of_pages, 10):
        threads.append(threading.Thread(target=proffessorrating_parser_wrapper, args=(page_num, ratings)))
    [thread.start() for thread in threads]
    [thread.join() for thread in threads]

    # create ratings dict for those teachers who:
    #    1) have non-zero rating
    #    2) are in teachers list
    teachers = set(teachers)
    ratings_for_existing_teachers = {
        name: val for name, val in ratings.items() if name in teachers
    }

    # if dict is non-empty
    if ratings_for_existing_teachers:
        return (0, ratings_for_existing_teachers)

    # when some type of error happened
    return (-1, 0)


def get_rating_wrapper(mode, teachers, container):
    """
    wrapper for functions getting rating. It allows multithreading

    args:
        mode - string defining what function would be called:
            'vk' or 'prof_rat'. If not, exception wil be raised
        teachers - object representing teachers' names. Will be passed to functions
        container - container to store returned value

    addition to container:{
        <mode>:<data returned by corresponding functions>
    }
    if error occurred, then data won't be written to container, which will later cause abortion of getting rating
    """
    if mode == 'vk':
        func = get_ratings_from_vk
    elif mode == 'prof_rat':
        func = get_rating_from_professorrating
    else:
        raise WrongModeException('Wrong mode for rating wrapper!')

    err, ratings = func(teachers)
    if not err:
        container[mode] = ratings


def rating_format(rating, mode):
    """
    format rating given the certain format

    args:
        rating - object, containing data to format:
            for vk it is {'up':.., 'down':.., 'neutral':.., 'total':..},
            for prof_rat it is float conversed to string
        mode - 'vk' or 'prof_rat'(if not, exception raised), by which data will be formatted

    return:
        formatted string
    """
    if mode == 'vk':
        return '{:.1f}-{:.1f}-{:.1f} | {} '.format(rating['up'],
                                                   rating['down'],
                                                   rating['neutral'],
                                                   rating['total'], )
    elif mode == 'prof_rat':
        return '{}'.format(rating)
    else:
        raise WrongModeException(' in rating_format()!')


def parse_teachers(html_text):
    """
    parses html_text from page with teachers list and finds all data about them

    returns dict - {
            <name>:{
                'degree':..,
                'department':..,
                'rank':..
            }
        }
    """

    html_text = html_text.replace('\n', '')  # because \n is terminating symbol for regex

    # this pattern finds all rows, each of which contains data about teacher
    pattern_for_rows = r'<tr.*?>(.*?)<\/tr>'
    rows = re.findall(pattern_for_rows, html_text)

    # pattern to find all possible data(name, department etc.)
    # fetches data between opening and closing tags of one type => 1st captured group would be tag, which is not needed
    data_from_row_pattern = r'<([\w\-]*)[^<>]*?>([^<>]*)<\/\1>'
    data_from_row_compiled = re.compile(data_from_row_pattern)
    # to check if name is valid, because previous patterns can give some rubbish
    name_check = re.compile(r'.*[а-яА-Я]+.*')

    teachers_data = {}
    for row in rows:
        teacher_data = data_from_row_compiled.findall(row)
        # label[1] because 1st group is tag
        teacher_data = [label[1] for label in teacher_data]
        # teacher_data contains 0-name, 1-degree, 2-department, 3-rank

        teacher_name = teacher_data[0].replace('ё', 'е')
        # if row contains a teacher
        if name_check.search(teacher_name):
            teachers_data[teacher_name] = dict(zip(
                ('degree', 'department', 'rank'),
                teacher_data[1:4]
            ))

    return teachers_data


def parse_departments(html_text):
    """
    parses html_text from page with departments list finds list of depts.

    return:
        departments_list
    """
    pattern_for_dept = r'<li><a.*?>(.*?)<\/a><\/li>'
    departments_list = re.findall(pattern_for_dept, html_text)

    return departments_list


def try_getting_response(url, post_args=None, method=''):
    """
    function tries to get post request
    args:
        url
        method - pass method to post request(like 'something.php')
        post_args - arguments for post request
    return:
        error,
        requests.Response object
    errors:
        0 OK
        -1 if wrong url or can't reach
    """
    # format url to use method
    if post_args is None:
        post_args = {}

    if not url.endswith('/'):
        url += '/'
    url += method

    try:
        response = requests.post(url, post_args)
        # if response is good
        if response.status_code == 200:
            return (0, response)
    except:
        pass
    return (-1, None)


class WrongModeException(Exception):
    """
    used in functions that get mode as one of args.
    if mode is wrong this exception is raised.
    must not raise in final program version
    """
    pass


if __name__ == '__main__':
    main()
