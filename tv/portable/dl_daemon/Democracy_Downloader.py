# Democracy download daemon Copyright (c) 2006 Participatory Culture Foundation
# Background process

# Make all output flush immediately.
import sys
import util
sys.stdout = util.AutoflushingStream(sys.stdout)
sys.stderr = util.AutoflushingStream(sys.stderr)

import os
from dl_daemon import daemon

port = int(os.environ['DEMOCRACY_DOWNLOADER_PORT'])
server = daemon.DownloaderDaemon(port)

from dl_daemon import download, command
download.startBTDownloader()
c = command.ReadyCommand(server)
c.send(block = False, retry = True)
