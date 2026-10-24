import pytest
from llmloop.memory_frontend import translate_memory_c
from llmloop.counted_c import translate_counted_memory_c
from llmloop.ordered_c import translate_ordered_c
from llmloop.cfg_frontend import translate_cfg_smt_c
from llmloop.private_allocations import PrivateAllocations


@pytest.mark.parametrize('qualifier',['static','volatile','const'])
@pytest.mark.parametrize('frontend',[translate_memory_c,translate_cfg_smt_c,translate_ordered_c])
def test_unmodeled_storage_cannot_be_reset_as_fresh_local_state(qualifier,frontend):
    source=f'int f(int n){{{qualifier} int x=0;int i=0;while(i<n){{x=x+1;i=i+1;}}return x;}}'
    with pytest.raises(ValueError,match='unqualified automatic'):frontend(source)


def test_repeated_static_local_is_not_folded_as_per_iteration_private_state():
    source='int f(int n){int x=0;int i=0;for(i=0;i<n;i=i+1){static int y=0;int *p=calloc(1,sizeof(int));y=y+1;x=x+y;free(p);}return x;}'
    with pytest.raises(ValueError,match='unqualified automatic'):PrivateAllocations(source,parameter_mins={'n':0})
