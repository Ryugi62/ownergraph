import asyncio, os, json
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
async def main():
    env=dict(os.environ); env["OWNERGRAPH_DB"]="data/mcp.db"; env.pop("GEMINI_API_KEY",None)
    params=StdioServerParameters(command=".venv/bin/python", args=["-m","ownergraph","mcp"], env=env)
    async with stdio_client(params) as (r,w):
        async with ClientSession(r,w) as s:
            await s.initialize()
            tools=await s.list_tools(); print(sorted(t.name for t in tools.tools))
            res=await s.call_tool("explain_feature_gate",{"gate_or_kep":"SidecarContainers"})
            txt=res.content[0].text; j=json.loads(txt); print(j['abstained'], j['evidence']['rows'][0]['kep'], j['evidence']['urls'])
            res=await s.call_tool("stale_decisions",{}); print(json.loads(res.content[0].text)['evidence']['rows'][:2])
asyncio.run(main())
