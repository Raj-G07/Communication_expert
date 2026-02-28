import logging
logging.basicConfig(level=logging.INFO)
try:
    from vision_agents.plugins import getstream
    import sys
    with open("check_out.txt", "w") as f:
        f.write("Edge dir:\n")
        f.write("\n".join(dir(getstream.Edge)))
        f.write("\n\nAgent dir:\n")
        from vision_agents.core.agents import agents
        f.write("\n".join(dir(agents.Agent)))
except Exception as e:
    with open("check_out.txt", "w") as f:
        f.write(str(e))
