from aws_cdk import (
    Stack,
    aws_ec2 as ec2,
    aws_ecs as ecs,
    aws_ecs_patterns as ecs_patterns,
    aws_iam as iam,
    aws_autoscaling as autoscaling,
    aws_logs as logs,
)
from constructs import Construct

class SpectraSightElbStramDemoStack(Stack):
    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        # ✅ Create a VPC with public & private subnets
        vpc = ec2.Vpc(self, "SightApiVpc", max_azs=2)

        # ✅ Create an ECS Cluster with EC2 launch type (not Fargate)
        cluster = ecs.Cluster(self, "SightApiCluster", vpc=vpc, cluster_name="spectra-sightapi-elb-stream-cluster")

        # ✅ Create EC2 instance role and security group
        ec2_role = iam.Role(self, "EC2InstanceRole",
            assumed_by=iam.ServicePrincipal("ec2.amazonaws.com"),
            managed_policies=[
                iam.ManagedPolicy.from_aws_managed_policy_name("AmazonSSMManagedInstanceCore"),
                iam.ManagedPolicy.from_aws_managed_policy_name("service-role/AmazonEC2ContainerServiceforEC2Role")
            ]
        )

        sg = ec2.SecurityGroup(self, "EC2SecurityGroup", vpc=vpc)

        # ✅ Create an Auto Scaling Group (ASG)
        asg = autoscaling.AutoScalingGroup(self, "SightApiASG",
                                        vpc=vpc,
                                        instance_type=ec2.InstanceType("m6a.xlarge"),
                                        machine_image=ec2.AmazonLinuxImage(),
                                        min_capacity=2,
                                        max_capacity=4,
                                        role=ec2_role,
                                        security_group=sg)

        # ✅ Create a Capacity Provider and add it to the cluster
        capacity_provider = ecs.AsgCapacityProvider(self, "AsgCapacityProvider", auto_scaling_group=asg)
        cluster.add_asg_capacity_provider(capacity_provider)

        # ✅ Define the ECS Task Definition & Container
        task_definition = ecs.Ec2TaskDefinition(
            self,
            "SightApiTaskDef",
        )

        container = task_definition.add_container(
            "SightApiContainer",
            image=ecs.ContainerImage.from_registry(
                "054037105643.dkr.ecr.ap-south-1.amazonaws.com/sight-api-vidproc-kinesis:latest"
            ),
            memory_limit_mib=1024,  # ✅ Set memory inside container definition
            cpu=512,  # ✅ Set CPU inside container definition
            logging=ecs.LogDrivers.aws_logs(stream_prefix="SightApiLogs"),
        )

        # ✅ Define container port mapping
        container.add_port_mappings(
            ecs.PortMapping(container_port=5000)  # Ensure this matches your app's port
        )

        # ✅ Create an ECS Service with EC2 Launch Type
        ec2_service = ecs.Ec2Service(
            self,
            "SightApiEc2Service",
            cluster=cluster,
            task_definition=task_definition,
            desired_count=2,  # Adjust based on load
        )

        # ✅ Create a Load Balanced Service (ALB)
        load_balanced_service = ecs_patterns.ApplicationLoadBalancedEc2Service(
            self,
            "SightApiEc2LoadBalancedService",
            cluster=cluster,
            task_definition=task_definition,
            load_balancer_name="elb-spectra-sightapi-stream",
            public_load_balancer=True,  # Set False if private
        )

        # ✅ Auto-scaling configuration (for ECS service, not ASG)
        scaling = load_balanced_service.service.auto_scale_task_count(max_capacity=4)
        scaling.scale_on_cpu_utilization(
            "CpuScaling",
            target_utilization_percent=50,
        )

        # ✅ Output Load Balancer DNS Name
        self.lb_dns = load_balanced_service.load_balancer.load_balancer_dns_name
