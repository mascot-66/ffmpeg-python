from __future__ import unicode_literals

from .dag import topo_sort
from functools import reduce
from past.builtins import basestring
import copy
import operator
import subprocess as _subprocess

from ._ffmpeg import (
    input,
    output,
    overwrite_output,
)
from .nodes import (
    GlobalNode,
    InputNode,   
    OutputNode,
    output_operator,
    Stream,
)


def _get_stream_name(name):
    return '[{}]'.format(name)


def _convert_kwargs_to_cmd_line_args(kwargs):
    args = []
    for k in sorted(kwargs.keys()):
        v = kwargs[k]
        args.append('-{}'.format(k))
        if v:
            args.append('{}'.format(v))
    return args


def _get_input_args(input_node):
    if input_node.name == input.__name__:
        kwargs = copy.copy(input_node.kwargs)
        filename = kwargs.pop('filename')
        fmt = kwargs.pop('format', None)
        video_size = kwargs.pop('video_size', None)
        args = []
        if fmt:
            args += ['-f', fmt]
        if video_size:
            args += ['-video_size', '{}x{}'.format(video_size[0], video_size[1])]
        args += _convert_kwargs_to_cmd_line_args(kwargs)
        args += ['-i', filename]
    else:
        raise ValueError('Unsupported input node: {}'.format(input_node))
    return args


def _get_filter_spec(i, node, stream_name_map):
    stream_name = _get_stream_name('v{}'.format(i))
    stream_name_map[node] = stream_name
    inputs = [stream_name_map[edge.upstream_node] for edge in node.incoming_edges]
    filter_spec = '{}{}{}'.format(''.join(inputs), node._get_filter(), stream_name)
    return filter_spec


def _get_filter_arg(filter_nodes, stream_name_map):
    filter_specs = [_get_filter_spec(i, node, stream_name_map) for i, node in enumerate(filter_nodes)]
    return ';'.join(filter_specs)


def _get_global_args(node):
    if node.name == overwrite_output.__name__:
        return ['-y']
    else:
        raise ValueError('Unsupported global node: {}'.format(node))


def _get_output_args(node, stream_name_map):
    if node.name != output.__name__:
        raise ValueError('Unsupported output node: {}'.format(node))
    args = []
    assert len(node.incoming_edges) == 1
    stream_name = stream_name_map[node.incoming_edges[0].upstream_node]
    if stream_name != '[0]':
        args += ['-map', stream_name]
    kwargs = copy.copy(node.kwargs)
    filename = kwargs.pop('filename')
    fmt = kwargs.pop('format', None)
    if fmt:
        args += ['-f', fmt]
    args += _convert_kwargs_to_cmd_line_args(kwargs)
    args += [filename]
    return args


@output_operator()
def get_args(stream):
    """Get command-line arguments for ffmpeg."""
    if not isinstance(stream, Stream):
        raise TypeError('Expected Stream; got {}'.format(type(stream)))
    args = []
    # TODO: group nodes together, e.g. `-i somefile -r somerate`.
    sorted_nodes, outgoing_edge_maps = topo_sort([stream.node])
    input_nodes = [node for node in sorted_nodes if isinstance(node, InputNode)]
    output_nodes = [node for node in sorted_nodes if isinstance(node, OutputNode) and not
        isinstance(node, GlobalNode)]
    global_nodes = [node for node in sorted_nodes if isinstance(node, GlobalNode)]
    filter_nodes = [node for node in sorted_nodes if node not in (input_nodes + output_nodes + global_nodes)]
    stream_name_map = {node: _get_stream_name(i) for i, node in enumerate(input_nodes)}
    filter_arg = _get_filter_arg(filter_nodes, stream_name_map)
    args += reduce(operator.add, [_get_input_args(node) for node in input_nodes])
    if filter_arg:
        args += ['-filter_complex', filter_arg]
    args += reduce(operator.add, [_get_output_args(node, stream_name_map) for node in output_nodes])
    args += reduce(operator.add, [_get_global_args(node) for node in global_nodes], [])
    return args


@output_operator()
def run(node, cmd='ffmpeg'):
    """Run ffmpeg on node graph."""
    if isinstance(cmd, basestring):
        cmd = [cmd]
    elif type(cmd) != list:
        cmd = list(cmd)
    args = cmd + node.get_args()
    _subprocess.check_call(args)


__all__ = [
    'get_args',
    'run',
]
