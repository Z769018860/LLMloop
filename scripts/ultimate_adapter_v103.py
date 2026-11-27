"""Use an unmodified Ultimate release with explicit JVM resource settings.
No logical configuration or solver change. The exact Java invocation is logged.
"""
import importlib.util,os,sys
from pathlib import Path
p=Path(os.environ['V103_ULTIMATE'])/'Ultimate.py';spec=importlib.util.spec_from_file_location('ultimate_upstream',p);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
m.memory_heap_size_max='1G'
original=m.create_ultimate_base_call
m.create_ultimate_base_call=lambda: original()[:1]+['-XX:ActiveProcessorCount=1']+original()[1:]
m.main()
