from wtforms import Form, BooleanField, StringField, PasswordField, validators
from .db import engine, engine_nl, engine_test
from collections import OrderedDict
import psycopg2
import psycopg2.extras
#import sqlite3 as sl #testing
import json #testing
from datetime import datetime #testing
from dateutil import tz, parser #testing
import pytz
from .views import app

def file_list_form_builder(formobj, runlists, data):
    class FileListForm(Form):
        pass

    # if formobj == -1:
    for (i, listname) in enumerate(runlists.keys()):
        listnum = runlists[listname]
        if listnum in data and formobj == -1:
            setattr(FileListForm, '%s' % listname, BooleanField(label=listname, default='checked'))
        else:
            setattr(FileListForm, '%s' % listname, BooleanField(label=listname))

        setattr(FileListForm, 'name', StringField('Name', [validators.Length(min=1), validators.InputRequired(), validators.Regexp('[A-Za-z0-9\s]{1,}', message='First and second name required.')]))
        setattr(FileListForm, 'comment', StringField('Comment', [validators.InputRequired()]))
        setattr(FileListForm, 'password', PasswordField('Password', [validators.InputRequired()]))

    if formobj != -1:
        return FileListForm(formobj)
    else:
        return FileListForm()

def get_current_lists_run(run):
    conn = engine.connect()
    result = conn.execute("SELECT list FROM evaluated_runs WHERE run={}".format(run))
    return [int(row[0]) for row in result.fetchall()]

def get_run_lists():
    conn = engine.connect()
    result = conn.execute("SELECT name, id FROM run_lists ORDER BY name ASC")
    data = OrderedDict();
    for entry in result.fetchall():
        data[str(entry[0])] = int(entry[1])
    conn.close()
    return data

def get_timestamp(local_tz=None, local=False, iso=False):
    if local_tz is None:
        local_tz = 'UTC'

    lcl_time = datetime.now(pytz.timezone(local_tz))
    utc_time = lcl_time.astimezone(pytz.utc)


    if local:
        timestamp = lcl_time
    else:
        timestamp = utc_time

    if iso:
        return timestamp.isoformat()
    else:
        return timestamp

def writeNewLists(inputTable, form, added, removed):
    newTable = inputTable
    newTable["pass"] += 1
    newTable["timestamp"] = get_timestamp(iso=True)
    newTable["name"] = form.name.data
    newTable["comment"] = form.comment.data
    if added: 
        newTable["list_added"] = [v for v in added]
    else:
        newTable["list_added"] = []
    if removed:
        newTable["list_removed"] = [v for v in removed]
    else:
        newTable["list_removed"] = []
    
    return newTable


def update_run_lists(form, run, lists, data, listHistory):
    """
    First update the run lists, then update the tables with new comment and timestamp
    """
    conn = psycopg2.connect(dbname=app.config['DB_NAME'],
                            user=app.config['DB_USER_EXPERT'],
                            host=app.config['DB_HOST'],
                            password=form.password.data)
    conn.set_isolation_level(psycopg2.extensions.ISOLATION_LEVEL_AUTOCOMMIT)

    cursor = conn.cursor()
    lists_added = []
    lists_removed = []
    for key in dir(form):
        if key in lists:
            if (getattr(form, key).data == True and lists[key] not in data): # need new entry
                lists_added.append(key)
                result = cursor.execute("INSERT INTO evaluated_runs(run, list, evaluator) VALUES({},{},'{}')".format(run, lists[key], form.name.data))
            elif (getattr(form, key).data == False and lists[key] in data): # need to delete entry
                result = cursor.execute("DELETE FROM evaluated_runs WHERE run = {} AND list = {}".format(run, lists[key]))
                lists_removed.append(key)
    
    """
    Now, update the nearlineDB with the name and time
    """

    conn_nl = psycopg2.connect(dbname=app.config['DB_NAME_NEARLINE'],
                               user="snotdaq",
                               host=app.config['DB_HOST_NEARLINE'],
                               password=app.config['DB_EXPERT_PASS_NEARLINE'],
                               port=app.config['DB_PORT_NEARLINE'])
    conn_nl.set_isolation_level(psycopg2.extensions.ISOLATION_LEVEL_AUTOCOMMIT)

    cursor_nl = conn_nl.cursor()
    result_nl = cursor_nl.execute("UPDATE run_selection SET name=%s, timestamp=now() WHERE run_min=%s AND run_max=%s AND type='RS_REPORT'", (form.name.data, run, run))

    # conn_nl = engine_nl.connect()
    # resultQuery = conn_nl.execute("UPDATE run_selection SET name=%s, timestamp=now() WHERE run_min=%s AND run_max=%s AND type='RS_REPORT'", (form.name.data, run, run))

    conn_nl.close()

    #temp testing locally

    #con_loc = sl.connect('/home/cm746/Documents/SNO+/Run_Selection/testMinardHistory/my-test.db')

    conn_test = psycopg2.connect(dbname=app.config['DB_NAME_TEST'],
                               user=app.config['DB_USER'],
                               host=app.config['DB_HOST_TEST'],
                               password=app.config['DB_PASS'])
    conn_test = engine_test.connect()
    # conn_test.set_isolation_level(psycopg2.extensions.ISOLATION_LEVEL_AUTOCOMMIT)
    # cursor_test = conn_test.cursor()

    newHistory = writeNewLists(listHistory[listHistory.keys()[-1]], form, lists_added, lists_removed)

    data = (newHistory["run_range"][0], newHistory["run_range"][1], newHistory["name"], "scintillator", "RS_UPLOAD", newHistory)
    conn_test.execute("INSERT INTO run_selection(run_min, run_max, name, criteria, type, meta_data) VALUES({}, {}, '{}', '{}', '{}', {})".format(newHistory["run_range"][0], newHistory["run_range"][1], newHistory["name"], "scintillator", "RS_UPLOAD", psycopg2.extras.Json(newHistory)))
    # conn_test.execute(sqlstr)

    # lists_to_update = []
    # for key in vars(form):
    #     if key in lists:
    #         if (getattr(form, key).data == True and lists[key] not in data) or (getattr(form, key).data == False and lists[key] in data):
    #             lists_to_update.append(key)

    # print("Lists to be updated:")
    # for i in lists_to_update:
    #     print(i)

def import_RS_ratdb(runs, result, limit, offset):

    if type(runs) == list:
        first_run = runs[0]
    else:
        first_run = runs

    query_string = """
        SELECT meta_data, name, timestamp
        FROM run_selection
        WHERE run_min <= {}
        AND run_max <= {}
        AND type='RS_REPORT'
        ORDER BY run_min DESC
        """.format(int(first_run + offset), first_run + limit + offset)

    query = """%s""" % query_string

    conn = engine_nl.connect()
    resultQuery = conn.execute(query)

    data = []
    names = []
    times = []
    criterialist = []
    for row in resultQuery.fetchall():
        data.append(row[0])
        names.append([row[1]])
        times.append([row[2]])
        if data[-1]['index'] not in criterialist:
            criterialist.append(data[-1]['index'])

    info = {}

    resultMapping = {'Pass': True, 'Purgatory': None, 'Fail': False, 'All': True}

    for i in range(len(data)):
        if (result == 'All' or data[i]['decision']['result'] == resultMapping[result]) and data[i]['version'] > 2:
            if int(data[i]['run_range'][0]) not in info.keys():
                info[int(data[i]['run_range'][0])] = {}
            info[int(data[i]['run_range'][0])][data[i]['index']] = data[i]
            info[int(data[i]['run_range'][0])][data[i]['index']]["name"] = names[i][0]
            info[int(data[i]['run_range'][0])][data[i]['index']]["time"] = times[i][0]

    if type(runs) == list:
        for number in runs:
            if int(number) not in info.keys():
                info[int(number)] = -1
            else:
                for criteria in criterialist:
                    if criteria not in info[int(number)].keys():
                        info[int(number)][criteria] = -1

    query_string = """
        SELECT meta_data
        FROM run_selection
        WHERE run_min <= {}
        AND type='CRITERIA'
        """.format(int(first_run), int(first_run))

    query = """%s""" % query_string
    resultQuery = conn.execute(query)

    criteriaInfo = {}

    for row in resultQuery.fetchall():
        criteriaInfo[row[0]["index"]] = row[0]

    conn.close()

    criteriaInfo = OrderedDict(sorted(criteriaInfo.items()))
    for v in criteriaInfo:
        criteriaInfo[v] = OrderedDict(sorted(criteriaInfo[v].items()))
        for k in criteriaInfo[v]:
            if isinstance(criteriaInfo[v][k], dict):
                criteriaInfo[v][k] = OrderedDict(sorted(criteriaInfo[v][k].items()))

    try:
        info = OrderedDict(sorted(info.items()))
        for v in info: #FIXME: Surely a more elegant way of doing this?
            info[v] = OrderedDict(sorted(info[v].items()))
            for k in info[v]:
                if isinstance(info[v][k], dict):
                    info[v][k] = OrderedDict(sorted(info[v][k].items()))
                for l in info[v][k]:
                    if isinstance(info[v][k][l], dict): #decision here!
                        info[v][k][l] = OrderedDict(sorted(info[v][k][l].items()))
                        for m in info[v][k][l]:
                            if isinstance(info[v][k][l][m], dict):
                                info[v][k][l][m] = OrderedDict(sorted(info[v][k][l][m].items()))
                                for n in info[v][k][l][m]:
                                    if isinstance(info[v][k][l][m][n], dict):
                                        info[v][k][l][m][n] = OrderedDict(sorted(info[v][k][l][m][n].items()))
                                        for o in info[v][k][l][m][n]:
                                            if isinstance(info[v][k][l][m][n][o], dict):
                                                info[v][k][l][m][n][o] = OrderedDict(sorted(info[v][k][l][m][n][o].items())) 
                            elif isinstance(info[v][k][l][m], list):
                                info[v][k][l][m] = sorted(info[v][k][l][m])
    except:
        pass

    #con_loc = sl.connect('/home/cm746/Documents/SNO+/Run_Selection/testMinardHistory/my-test.db')
    con_loc = engine_test.connect()
    # cursor_test = con_loc.cursor()
    listData = {}
    query_string = """
        SELECT meta_data
        FROM run_selection
        WHERE run_min >= {}
        AND run_max <= {}
        AND type='RS_UPLOAD'
        ORDER BY run_min DESC
        """.format(int(first_run + offset), first_run + limit + offset)

    query = """%s""" % query_string
    data = con_loc.execute(query)
    for row in data:
        # temp = json.loads(row[0])
        temp = row[0]
        listData[temp["pass"]] = temp
        #print (temp)

    return info, criteriaInfo, OrderedDict(sorted(listData.items()))
