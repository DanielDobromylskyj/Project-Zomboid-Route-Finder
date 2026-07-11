from satnav import render_engine

engine = render_engine.RenderEngine("data/streets.xml", "data/worldmap.xml", cache_name="b42.19.0")
engine.run()
