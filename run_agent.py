#!/usr/bin/env python3
import argparse, os
if __name__=='__main__':
    parser=argparse.ArgumentParser(description='Linkdesk Agent Workspace (local only)')
    parser.add_argument('--port',type=int,default=8860)
    args=parser.parse_args()
    import uvicorn
    uvicorn.run('agentdesk.web:app',host='127.0.0.1',port=args.port,log_level='warning')
