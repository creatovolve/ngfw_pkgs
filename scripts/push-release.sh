#!/bin/sh

sudo rsync -rlptvz -e ssh /var/www/metavize root@release.metavize.com:/var/www.release/
scp ~/work/pkgs/scripts/override.testing.metavize ~/work/pkgs/scripts/deb-scan.sh root@release.metavize.com:~/
ssh release.metavize.com -lroot "rm /var/www.release/metavize/pool/metavize/t/test-*"
ssh release.metavize.com -lroot "rm /var/www.release/metavize/pool/metavize/f/fprot-*"
ssh release.metavize.com -lroot "rm /var/www.release/metavize/pool/metavize/s/sophos-*"
ssh release.metavize.com -lroot "rm /var/www.release/metavize/pool/metavize/k/kernel-dev*"
ssh release.metavize.com -lroot "sh ~/deb-scan.sh /var/www.release/metavize "

