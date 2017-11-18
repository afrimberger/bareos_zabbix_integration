from socket import gethostname
try:
    import configparser
except ImportError:
    import ConfigParser as configparser
import itertools

server_type = "bareos"

conf = {
            'type' : server_type,
            'log_dir': "/var/log/{0}/".format(server_type),
            'zabbix_agent_conf': "/etc/zabbix/zabbix_agentd.conf",
            'zabbix_send_opts' : [], # e.g. ['--tls-connect', 'psk', '--tls-psk-identity', '...', '--tls-psk-file', '/etc/zabbix/zabbix_agentd.psk']
            'bconsole_conf_file': "/etc/{0}/bconsole.conf".format(server_type),
            'bconsole_wait': 5,
            'email_from': "{0} <{1}@{2}>".format(server_type, server_type.title(), gethostname()),
            'email_server': "127.0.0.1"
       }

zcfg = configparser.ConfigParser()
zcfg.readfp(itertools.chain(['[global]'], open(conf['zabbix_agent_conf'])))
zserver = zcfg.get('global', 'server').split(',')[0]

conf['hostname'] = gethostname()
conf['zabbix_server'] = zserver
