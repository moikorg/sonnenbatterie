import requests
import sqlite3
import time
import sys

def getFirstArgument():
    if len(sys.argv) > 1:
        try:
            argument = float(sys.argv[1])
        except ValueError:
            return 10   # default 10 sec
        return argument
    return 10   # default 10 secs

def getSonnenData():
    try:
        r = requests.get('http://SB-41059:8080/api/v1/status')
        return r.json()
    except requests.exceptions.ConnectionError as err:
        print ("Error, connection to sonnen battery could be established")
        print (err)
        return None

def str2Epoch(strDate):
    pattern = '%Y-%m-%d %H:%M:%S'
    return int(time.mktime(time.strptime(strDate, pattern)))

def main():
    period = getFirstArgument()
    conn = sqlite3.connect('sonnen.sql')
    c = conn.cursor()

#    sqlSelect = "SELECT * FROM battery"
    sqlInsert = """
        INSERT INTO battery
        (consumption, frequency, gridConsumption, isSystemInstalled, pacTotal, production, rsoc, timestamp, ts, usoc,
        uAC, uBat)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)"""

#    for row in c.execute(sqlSelect):
#        print(row)

    while True:
        sonnenData = getSonnenData()
        if sonnenData == None:
            time.sleep(period - 0.1)
            continue

        ts = str2Epoch(sonnenData['Timestamp'])
        myrow = (
            sonnenData['Consumption_W'],
            sonnenData['Fac'],
            -sonnenData['GridFeedIn_W'],
            sonnenData['IsSystemInstalled'],
            -sonnenData['Pac_total_W'],
            sonnenData['Production_W'],
            sonnenData['RSOC'],
            sonnenData['Timestamp'],
            ts,
            sonnenData['USOC'],
            sonnenData['Uac'],
            sonnenData['Ubat']
        )
        c.execute(sqlInsert, myrow)

        conn.commit()
        time.sleep(period-0.1)

    conn.close()

# this is the standard boilerplate that calls the main() function
if __name__ == '__main__':
    # sys.exit(main(sys.argv)) # used to give a better look to exists
    main()