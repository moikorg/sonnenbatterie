import requests
import time
import argparse
from time import gmtime, strftime
import logging
import mysql.connector
import configparser
import paho.mqtt.client as mqtt


def configSectionMap(config, section):
    dict1 = {}
    options = config.options(section)
    for option in options:
        try:
            dict1[option] = config.get(section, option)
            if dict1[option] == -1:
                print("skip: %s" % option)
                logging.warning("skip: %s" % option)
        except:
            print("exception on %s!" % option)
            logging.warning("exception on %s!" % option)
            dict1[option] = None
    return dict1


def connectDB(configfile):
    config = configparser.ConfigParser()
    config.read(configfile)

    conn = mysql.connector.connect(host=configSectionMap(config, "DB")['host'],
                                   user=configSectionMap(config, "Credentials")['username'],
                                   password=configSectionMap(config, "Credentials")['password'],
                                   db=configSectionMap(config, "DB")['db'],
                                   port=configSectionMap(config, "DB")['port'],
                                   charset = 'utf8')
    return conn


def parseTheArgs() -> object:
    parser = argparse.ArgumentParser(description='Request the Sonnen Battery API and write the data to the SQL DB')
    parser.add_argument('-p', type=int,
                        help='an integer for the time in seconds to wait until two API requests (default: 30sec)',
                        default=10)
    parser.add_argument('-d', dest='verbose', action='store_true',
                        help='print debugging information')
#    parser.add_argument('db', metavar='database', type=str,
#                        help='the complete path/name to the DB')
    parser.add_argument('-m', dest='mock', action='store_true',
                        help='use mocked data instead requesting from the API')
#    parser.add_argument('-l', help='path and filename of logfile, default=/var/log/sonnen.json',
#                        default='/var/log/sonnen.json')
    parser.add_argument('-1', dest='oneshot', action='store_true',
                        help='one shot execution',)
    parser.add_argument('-f', help='path and filename of the config file, default is ./config.rc',
                        default='./config.rc')
    parser.add_argument('-v', help='if this argument is set, then output is logged to /tmp/sonnen.log',
                        action='store_true')

    args = parser.parse_args()
    return args


def getSonnenData():
    try:
        r = requests.get('http://SB-41059:8080/api/v1/status', timeout=1.0)
        return r.json()
    except requests.exceptions.ConnectionError as err:
        logging.error("Error, could not connect to Sonnen-Battery API. %s" % err)
        print("Error, connection to sonnen battery could be established")
        print(err)
        return None
    except requests.exceptions.Timeout as err:
        logging.error("Request timed out. %s" % err)
        print("Request to battery timed out")
        print(err)


def str2Epoch(strDate):
    pattern = '%Y-%m-%d %H:%M:%S'
    return int(time.mktime(time.strptime(strDate, pattern)))

def on_connect(client, userdata, flags, rc):
    if rc==0:
        print("connected OK Returned code=",rc)
    else:
        print("Bad connection Returned code=",rc)

def main():
    args = parseTheArgs()
    period = args.p

    if args.v == True:
        logging.basicConfig(filename='/tmp/sonnen.log',format='%(asctime)s %(message)s',level=logging.INFO)

    mqttClient = connectMQTT(args)

    conn = connectDB(args.f)
    c = conn.cursor()

    sqlInsert = """
        INSERT INTO sonnen_sonnenbattery
        (consumption, gridConsumption, pacTotal, production, rsoc, usoc,
        uAC, uBat, timestamp)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)"""

    while True:
        if args.mock:
            sonnenData={}
            sonnenData['Consumption_W'] = 6182
            sonnenData['GridFeedIn_W'] = -780
            sonnenData['Pac_total_W'] = 2501
            sonnenData['Production_W'] = 2900
            sonnenData['RSOC'] = 5
            sonnenData['Timestamp'] = strftime("%Y-%m-%d %H:%M:%S", gmtime())
            sonnenData['USOC'] = 0
            sonnenData['Uac'] = 230
            sonnenData['Ubat'] = 48
        else:
            sonnenData = getSonnenData()
            if sonnenData == None:
                error_str = "Could not connect to sonnen battery. Retry in " + str(period) + "seconds"
#                if args.verbose is True:
                print(error_str)
                logging.error(error_str)
                time.sleep(period - 0.3)
                continue


            try:
                output_str = "{\"time\":\""+sonnenData['Timestamp']+"\","+\
                         "\"consumption\":"+str(sonnenData['Consumption_W'])+","+\
                         "\"gridfeedin\":"+str(sonnenData['GridFeedIn_W'])+","+ \
                         "\"pactotal\":" + str(sonnenData['Pac_total_W'])+"," + \
                         "\"production\":" + str(sonnenData['Production_W'])+"," + \
                         "\"rsoc\":" + str(sonnenData['RSOC'])+"," + \
                         "\"usoc\":" + str(sonnenData['USOC'])+"," + \
                         "\"ubat\":" + str(sonnenData['Ubat'])+"}"
                mqtt_json = "{\"ts\":\"" + sonnenData['Timestamp'] + "\"," + \
                             "\"cons\":" + str(sonnenData['Consumption_W']) + "," + \
                             "\"gridFIn\":" + str(sonnenData['GridFeedIn_W']) + "," + \
                             "\"pactot\":" + str(sonnenData['Pac_total_W']) + "," + \
                             "\"prod\":" + str(sonnenData['Production_W']) + "," + \
                             "\"usoc\":" + str(sonnenData['USOC']) + "}"
            except KeyError as err:
                logging.warning("KeyError occured: %s" % err)
            else:
                if args.verbose:
                    print(output_str)
                    logging.info(output_str)

        try:
            myrow = (
                sonnenData['Consumption_W'],
                sonnenData['GridFeedIn_W'],
                sonnenData['Pac_total_W'],
                sonnenData['Production_W'],
                sonnenData['RSOC'],
                sonnenData['USOC'],
                sonnenData['Uac'],
                sonnenData['Ubat'],
                sonnenData['Timestamp'],
            )
        except KeyError:
            print("some keys are missing, rollingback")
            #conn.rollback()
        else:
            if sonnenData['Consumption_W'] > 0:
                diff = abs(sonnenData['Production_W']+sonnenData['Pac_total_W']-
                       sonnenData['Consumption_W']-sonnenData['GridFeedIn_W'])
                if diff > 20:
                    print("error in read out, diff greater than 20. Diff was: " + str(diff))
                else:
                    try:
                        c.execute(sqlInsert, myrow)
                    except mysql.connector.errors.DatabaseError:
                        print("connection to DB did not work")
                    else:
                        conn.commit()

                    mqttClient.publish("sensor/pv/1", mqtt_json)  # publish
            else:
                print("got a 0 consumption, ignore this data set")
        if args.oneshot:
            break

        time.sleep(period-0.05)

    conn.close()
    mqttClient.disconnect()

def on_disconnect(client, userdata, rc):
    print("disconnecting reason  " + str(rc))


# The callback for when the client receives a CONNACK response from the server.
def on_connect(client, userdata, flags, rc):
    print("Connected with result code "+str(rc))
    # Subscribing in on_connect() means that if we lose the connection and
    # reconnect then subscriptions will be renewed.
   #client.subscribe("$SYS/#")


def on_publish(client, userdata, result):
    print("Data published")
    pass


def connectMQTT(args):
    config = configparser.ConfigParser()
    config.read(args.f)
    broker = configSectionMap(config, "MQTT")['host']

    client = mqtt.Client()
    client.on_connect = on_connect
    client.on_publish = on_publish
    client.on_disconnect = on_disconnect
    client.username_pw_set(username=configSectionMap(config, "MQTT")['username'],
                           password= configSectionMap(config, "MQTT")['password'])

    try:
        client.connect(broker, 1883, 60)
    except:
        print("ERROR: Can not connect to MQTT broker")
        return 1

    print("ready for publishing")
    return client

# this is the standard boilerplate that calls the main() function
if __name__ == '__main__':
    # sys.exit(main(sys.argv)) # used to give a better look to exists
    main()
