if [ $HOSTNAME == 'ip-172-31-42-131' ]; then
	echo "1" > /home/ec2-user/cs244b-project/zoo_exp2/myid
	ZOOCFGDIR=/home/ec2-user/cs244b-project/zoo_exp2/zoo1 \
		/home/ec2-user/cs244b-project/zookeeper/bin/zkServer.sh start-foreground
elif [ $HOSTNAME == 'ip-172-31-13-236' ]; then
	echo "2" > /home/ec2-user/cs244b-project/zoo_exp2/myid
	ZOOCFGDIR=/home/ec2-user/cs244b-project/zoo_exp2/zoo2 \
		/home/ec2-user/cs244b-project/zookeeper/bin/zkServer.sh start-foreground
elif [ $HOSTNAME == 'ip-10-81-194-112' ]; then
	echo "3" > /home/ec2-user/cs244b-project/zoo_exp2/myid
	ZOOCFGDIR=/home/ec2-user/cs244b-project/zoo_exp2/zoo3 \
		/home/ec2-user/cs244b-project/zookeeper/bin/zkServer.sh start-foreground
fi
