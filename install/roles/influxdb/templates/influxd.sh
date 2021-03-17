#!/bin/sh

cd `dirname $0` 

start(){
   nohup usr/bin/influxd --config influxdb.conf >influxd.log 2>&1 &
   sleep 1
}

stop(){
   pkill -TERM -x influxd
   sleep 1
}
check_process(){
   pgrep -x influxd >/dev/null 2>&1
}


case "$1" in
   start)
      check_process && (echo Allready started; exit 1)
      start
      if check_process; then
         echo Started...
      else
         echo Failed...
      fi
      ;;
   stop)
      check_process || (echo Not started; exit 1 )
      stop
      if check_process; then
         echo Not stopped...
      else
         echo Stopped...
      fi
      ;;
   restart)
      stop
      start
      ;;
   *)
      echo "Usage: `basename $0` start|stop|restart"
esac
exit 0
