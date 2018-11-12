# netapp-nfslockcheck
Python script to check NetApp cluster for NFS locks and migrate affected LIFs if lock threshold is hit

Note : You will need the NetApp Python SDK. Due to it's license I cannot provide it here. 
https://community.netapp.com/t5/Developer-Network-Articles-and-Resources/NetApp-Manageability-NM-SDK-Introduction-and-Download-Information/ta-p/86418

We hit an interesting bug where the number of NFS locks would hit the node threshold level. (500,000) Once that number was reached no new NFS locks could be granted. In order to reduce the potential impact I created this script which checks the number of locks and triggers all LIFs on the impacted node to be migrated to the other node. This will reset the lock #. 

It logs the number of locks on each run to a specified CloudWatch log group and will trigger an SMS message if that threshold is reached. 

TODO : 
Make my project a lot more user friendly ( Deployment instructions for python environment )
Scan for all NFS enabled LIFs on specified node ( Currently only checks for LIFs within specified vserver )

