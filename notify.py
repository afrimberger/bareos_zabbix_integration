#!/usr/bin/env python3.4

import sys
import subprocess
import re
import os
import argparse
from argparse import RawTextHelpFormatter
import logging
import smtplib
from email.mime.text import MIMEText
import tempfile
import subprocess

# Settings
from conf import conf


# Example used for testing:
# cat test/report-some.host.txt | ./notify.py "some.host" "Backup" "F" "OK"

def sendmail(jname, jtype, jlevel, jexit_code, jmsg, recipients, job_client):
    if job_client:
        subject = "Bareos: {0} {1} of {2} on {3} {4}".format(jtype, jexit_code, jname, job_client, jlevel)
    else:
        subject = "Bareos: {0} {1} of {2} {3}".format(jtype, jexit_code, jname, jlevel)
    
    logging.debug("sending email ({0}) to '{1}'".format(subject, recipients))

    msg = MIMEText(jmsg)
    msg['Subject'] = subject
    msg['From'] = conf['email_from']
    msg['To'] = ', '.join(recipients)

    s = smtplib.SMTP( conf['email_server'] )
    s.sendmail( conf['email_from'], recipients, msg.as_string() )
    s.quit()


def send_to_zabbix(metrics):
    with tempfile.NamedTemporaryFile(delete=True) as f:
        for k, v in metrics.items():
            f.write(bytes("%s %s %s\n" % (conf['hostname'], k, v), 'UTF-8'))

        f.flush()
        print(f.name)
        cmd = ['zabbix_sender', '-z', conf['zabbix_server'], '-i', f.name]
        cmd.append(conf['zabbix_send_opts'])
        if logging.getLogger().getEffectiveLevel() == logging.DEBUG:
            cmd.append('-vv')
        print(cmd)
        logging.info("sending metrics to '{0}': '{1}'".format(conf['zabbix_server'], metrics))
        subprocess.check_call(cmd)
        #send_to_zabbix(metrics, conf['zabbix_server'], 10051, 20)


logging.basicConfig(
    format=u'%(levelname)-8s [%(asctime)s] %(message)s',
    level=logging.DEBUG,
    filename=u'{0}/{1}.log'.format(conf['log_dir'], os.path.basename(__file__))
)
logging.info('sys.argv: ' + repr(sys.argv))

parser = argparse.ArgumentParser(
            formatter_class=RawTextHelpFormatter,
            description=
"""Simple script to send Bareos reports to Zabbix.
Should be used in Bareos-dir config instead of mail command:
    mail = <admin@localhost> = all, !skipped
    mailcommand = "{0} '%n' '%t' '%l' '%e' [--job-client '%c'] [--recipients '%r'] [--email-on-fail] [--email-on-success]"
Hostnames in Zabbix and Bareos must correspond
""".format(os.path.realpath(__file__))
                                )

parser.add_argument('job_name', help='job name (%%n)')
parser.add_argument('job_type', help='job type (%%t)')
parser.add_argument('job_level', help='job level (%%l)')
parser.add_argument('job_exit_code', help='job exit code (%%e)')

parser.add_argument('--job-client',
                    help='job client (%%c)')
parser.add_argument('--recipients',
                    action='store',
                    type=lambda x: x.split(),
                    default=[],
                    help='space-separated list of report recipients (%%r)')
parser.add_argument('--email-on-fail',
                    action='store_true',
                    help='Send email about failed jobs to recipients')
parser.add_argument('--email-on-success',
                    action='store_true',
                    help='Send email about succeed jobs to recipients')

args = parser.parse_args()

# Define how to get values from input
tests = (

    ("\s*FD Files Written:\s+([0-9]+)\s*",
        "{0}.fd_fileswritten".format(conf['type']),
        lambda x: x.group(1)),

    ("\s*SD Files Written:\s+([0-9]+)\s*",
        "{0}.sd_fileswritten".format(conf['type']),
        lambda x: x.group(1)),

    ("\s*FD Bytes Written:\s+([0-9][,0-9]*)\s+\(.*\)\s*",
        "{0}.fd_byteswritten".format(conf['type']),
        lambda x: x.group(1).replace(",", "")),

    ("\s*SD Bytes Written:\s+([0-9][,0-9]*)\.*",
        "{0}.sd_byteswritten".format(conf['type']),
        lambda x: x.group(1).replace(",", "")),

    ("\s*Last Volume Bytes:\s+([0-9][,0-9]*).*",
        "{0}.lastvolumebytes".format(conf['type']),
        lambda x: x.group(1).replace(",", "")),

    ("\s*Files Examined:\s+([0-9][,0-9]*)\s*",
        "{0}.verify_filesexamined".format(conf['type']),
        lambda x: x.group(1).replace(",", "")),

    ("\s*Non-fatal FD errors:\s+([0-9]+)\s*",
        "{0}.fd_errors_non_fatal".format(conf['type']),
        lambda x: x.group(1)),

    ("\s*SD Errors:\s+([0-9]+)\s*",
        "{0}.sd_errors".format(conf['type']),
        lambda x: x.group(1))

)

result = {}

in_msg = ""
# Get values from input
for line in sys.stdin.readlines():
    in_msg += line
    for regexp, key, value in tests:
        match = re.match(regexp, line)
        if match:
            # DEBUG
            logging.debug(line)
            result[key] = value(match)
            continue

if not result:
    # TODO: send email?
    logging.info("It is not a message about job")
    exit(0)

result['{0}.job_exit_code'.format(conf['type'])] = args.job_exit_code

logging.debug(repr(in_msg))
# DEBUG
logging.debug(repr(result))

metrics = dict()
for key, value in result.items():
    k = '{0}[{1}]'.format(key, args.job_name)
    metrics[k] = value

# Send result to zabbix
logging.info( "sending metrics to '{0}': '{1}'".format(conf['zabbix_server'], metrics) )
try:
    send_to_zabbix(metrics)
except subprocess.CalledProcessError as e:
    msg = "Failed sending metrics to Zabbix Server\n metrics=%s:\n command=%s" % (metrics, e)
    print(msg)
    logging.error(msg)


# Send emails (if requested)
if (args.recipients and
    ((args.job_exit_code == 'OK' and args.email_on_success) or
     (args.job_exit_code != 'OK' and args.email_on_fail))):
    sendmail(args.job_name, args.job_type, args.job_level, args.job_exit_code, in_msg, args.recipients, args.job_client)
