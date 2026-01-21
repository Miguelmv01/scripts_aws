{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "AllowDescribeAllEC2",
      "Effect": "Allow",
      "Action": "ec2:Describe*",
      "Resource": "*"
    },
    {
      "Sid": "AllowCreateRunStopInSpainCentral",
      "Effect": "Allow",
      "Action": [
        "ec2:RunInstances",
        "ec2:CreateTags",
        "ec2:StopInstances"
      ],
      "Resource": "*",
      "Condition": {
        "StringEquals": {
          "aws:RequestedRegion": "eu-south-2"
        }
      }
    },
    {
      "Sid": "DenyTerminateWithNoDeleteTag",
      "Effect": "Deny",
      "Action": "ec2:TerminateInstances",
      "Resource": "arn:aws:ec2:eu-south-2:*:instance/*",
      "Condition": {
        "StringEquals": {
          "ec2:ResourceTag/Role": "NoDelete"
        }
      }
    },
    {
      "Sid": "DenyTerminateAfter2025",
      "Effect": "Deny",
      "Action": "ec2:TerminateInstances",
      "Resource": "arn:aws:ec2:eu-south-2:*:instance/*",
      "Condition": {
        "DateGreaterThan": {
          "aws:CurrentTime": "2025-12-31T22:59:59Z"
        }
      }
    }
  ]
}
