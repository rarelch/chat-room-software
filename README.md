# Chat Room Software
> A LAN multi-user chatroom program for undergraduate course design.
> 本科课程设计项目：局域网多人聊天室软件

## Project Introduction
This is a simple chatroom system implemented by Python, based on TCP Socket communication.
Functions include user registration & login, friend management and real-time message sending.
It supports Wireshark to capture and analyze network traffic.

本项目是基于Python、TCP Socket实现的简易局域网聊天室系统。
实现用户注册登录、好友管理、实时消息收发功能，支持使用Wireshark抓取网络数据包。

## Environment Requirement
- Python 3.9
- Related dependent libraries

## Usage
1. Ensure all clients and the server are in the **same local area network(LAN)**.
2. Modify the IP address in `utils` file to the host machine's IP.
3. Run `server.py` on the host as server side.
4. Run `client.py` on client side. Complete registration, login and add friends, then you can start chatting.
5. You can use Wireshark to capture and analyze data packets during communication.

## Note
This project is completed for course design, only for learning purposes.
