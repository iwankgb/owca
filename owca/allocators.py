# Copyright (c) 2018 Intel Corporation
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
import math
from abc import ABC, abstractmethod
from enum import Enum
from pprint import pformat
from typing import List, Dict, Union, Tuple, Optional
import logging

from owca.logger import trace, TRACE
from owca.metrics import Metric, MetricType
from owca.mesos import TaskId
from owca.platforms import Platform
from owca.detectors import TasksMeasurements, TasksResources, TasksLabels, Anomaly

from dataclasses import dataclass

log = logging.getLogger(__name__)


class AllocationType(str, Enum):

    QUOTA = 'cpu_quota'
    SHARES = 'cpu_shares'
    RDT = 'rdt'


class MergeableAllocationValue(ABC):

    @abstractmethod
    def merge_with_current(self, current: 'MergeableAllocationValue') -> Tuple[
            'MergeableAllocationValue', 'MergeableAllocationValue']:
        ...


class SerializableAllocationValue(ABC):

    @abstractmethod
    def generate_metrics(self) -> List[Metric]:
        ...


@dataclass(unsafe_hash=True)
class RDTAllocation(SerializableAllocationValue, MergeableAllocationValue):
    # defaults to TaskId from TasksAllocations
    name: str = None
    # CAT: optional - when no provided doesn't change the existing allocation
    l3: str = None
    # MBM: optional - when no provided doesn't change the existing allocation
    mb: str = None

    def generate_metrics(self) -> List[Metric]:
        """Encode RDT Allocation as metrics.
        Note:
        - cache allocation: generated two metrics, with number of cache ways and
                            mask of bits (encoded as int)
        - memory bandwidth: is encoded as int, representing MB/s or percentage
        """
        # Empty object generate no metric.
        if not self.l3 and not self.mb:
            return []

        group_name = self.name or ''

        metrics = []
        if self.l3:
            domains = _parse_schemata_file_row(self.l3)
            for domain_id, raw_value in domains.items():
                metrics.extend([
                    Metric(
                        name='allocation', value=_count_enabled_bits(raw_value),
                        type=MetricType.GAUGE, labels=dict(
                            allocation_type='rdt_l3_cache_ways', group_name=group_name,
                            domain_id=domain_id)
                    ),
                    Metric(
                        name='allocation', value=int(raw_value, 16),
                        type=MetricType.GAUGE, labels=dict(
                            allocation_type='rdt_l3_mask', group_name=group_name,
                            domain_id=domain_id)
                    )
                ])

        if self.mb:
            domains = _parse_schemata_file_row(self.mb)
            for domain_id, raw_value in domains.items():
                # NOTE: raw_value is treated as int, ignoring unit used (MB or %)
                value = int(raw_value)
                metrics.append(
                    Metric(
                       name='allocation', value=value, type=MetricType.GAUGE,
                       labels=dict(allocation_type='rdt_mb',
                                   group_name=group_name, domain_id=domain_id)
                    )
                )

        return metrics

    @trace(log)
    def merge_with_current(self: Optional['RDTAllocation'],
                           current_rdt_allocation: 'RDTAllocation') -> \
            Tuple['RDTAllocation', 'RDTAllocation']:
        """Merge with existing RDTAllocation objects and return
        sum of the allocations (target_rdt_allocation) and allocations that need to be updated
        (rdt_allocation_changeset)."""
        new_rdt_allocation = self
        # new name, then new allocation will be used (overwrite) but no merge
        if current_rdt_allocation is None or current_rdt_allocation.name != new_rdt_allocation.name:
            log.debug('new name or no previous allocation exists')
            return new_rdt_allocation, new_rdt_allocation
        else:
            log.debug('merging existing rdt allocation')
            target_rdt_allocation = RDTAllocation(
                name=current_rdt_allocation.name,
                l3=new_rdt_allocation.l3 or current_rdt_allocation.l3,
                mb=new_rdt_allocation.mb or current_rdt_allocation.mb,
            )
            rdt_allocation_changeset = RDTAllocation(
                name=new_rdt_allocation.name,
            )
            if current_rdt_allocation.l3 != new_rdt_allocation.l3:
                rdt_allocation_changeset.l3 = new_rdt_allocation.l3
            if current_rdt_allocation.mb != new_rdt_allocation.mb:
                rdt_allocation_changeset.mb = new_rdt_allocation.mb
            return target_rdt_allocation, rdt_allocation_changeset


TaskAllocations = Dict[AllocationType, Union[float, RDTAllocation]]
TasksAllocations = Dict[TaskId, TaskAllocations]


@dataclass
class AllocationConfiguration:

    # Default value for cpu.cpu_period [ms] (used as denominator).
    cpu_quota_period: int = 1000

    # Number of minimum shares, when ``cpu_shares`` allocation is set to 0.0.
    cpu_shares_min: int = 2
    # Number of shares to set, when ``cpu_shares`` allocation is set to 1.0.
    cpu_shares_max: int = 10000

    # Default Allocation for default root group during initilization.
    # It will be used as default for all tasks (None will set to maximum available value).
    default_rdt_l3: str = None
    default_rdt_mb: str = None


class Allocator(ABC):

    @abstractmethod
    def allocate(
            self,
            platform: Platform,
            tasks_measurements: TasksMeasurements,
            tasks_resources: TasksResources,
            tasks_labels: TasksLabels,
            tasks_allocations: TasksAllocations,
    ) -> (TasksAllocations, List[Anomaly], List[Metric]):
        ...


class NOPAllocator(Allocator):

    def allocate(self, platform, tasks_measurements, tasks_resources,
                 tasks_labels, tasks_allocations):
        return [], [], []


# -----------------------------------------------------------------------
# private logic to handle allocations
# -----------------------------------------------------------------------

def _convert_tasks_allocations_to_metrics(tasks_allocations: TasksAllocations) -> List[Metric]:
    """Takes allocations on input and convert them to something that can be
    stored persistently as metrics adding type fields and labels.

    Simple allocations become simple metric like this:
    - Metric(name='allocation', type='cpu_shares', value=0.2, labels=(task_id='some_task_id'))
    Encoding RDTAllocation object is delegated to RDTAllocation class.
    """
    metrics = []
    for task_id, task_allocations in tasks_allocations.items():
        task_allocations: TaskAllocations
        for allocation_type, allocation_value in task_allocations.items():

            if isinstance(allocation_value, SerializableAllocationValue):
                this_allocation_metrics = allocation_value.generate_metrics()
                for metric in this_allocation_metrics:
                    metric.labels.update(task_id=task_id)
                metrics.extend(this_allocation_metrics)

            elif isinstance(allocation_value, (float, int)):
                # Default metrics encoding method for float and integers values.
                # Simple encoding for
                metrics.append(
                    Metric(name='allocation', value=allocation_value, type=MetricType.GAUGE,
                           labels=dict(allocation_type=allocation_type, task_id=task_id)
                           )
                )
            else:
                raise NotImplementedError(
                    'encoding AllocationType=%r for value of type=%r is '
                    'not supported!' % (allocation_type, type(allocation_value))
                )

    return metrics


# Defines how senstive in terms of float precision are changes from RDTAllocation detected.
FLOAT_VALUES_CHANGE_DETECTION = 1e-02


@trace(log, verbose=False)
def _calculate_task_allocations_changeset(
        current_task_allocations: TaskAllocations,
        new_task_allocations: TaskAllocations)\
        -> Tuple[TaskAllocations, TaskAllocations]:
    """Return tuple of resource allocation (changeset) per task.
    """
    # Copy current to become new current as target.
    target_task_allocations: TaskAllocations = dict(current_task_allocations)
    task_allocations_changeset: TaskAllocations = {}

    for allocation_type, new_allocation_value in new_task_allocations.items():
        if isinstance(new_allocation_value, MergeableAllocationValue):
            current_rdt_allocations = current_task_allocations.get(AllocationType.RDT)
            target_rdt_allocation, rdt_allocation_changeset = \
                new_allocation_value.merge_with_current(current_rdt_allocations)
            target_rdt_allocation: RDTAllocation
            rdt_allocation_changeset: RDTAllocation
            target_task_allocations[AllocationType.RDT] = target_rdt_allocation
            if rdt_allocation_changeset.l3 is not None or rdt_allocation_changeset.mb is not None:
                task_allocations_changeset[AllocationType.RDT] = rdt_allocation_changeset

        else:
            # Float and integered based change detection.
            if allocation_type in current_task_allocations:
                # If we have old value
                current_allocation_value = current_task_allocations[allocation_type]
                value_changed = not math.isclose(current_allocation_value, new_allocation_value,
                                                 rel_tol=FLOAT_VALUES_CHANGE_DETECTION)
            else:
                # There is no old value, so there is a change
                value_changed = True

            if value_changed:
                target_task_allocations[allocation_type] = new_allocation_value
                task_allocations_changeset[allocation_type] = new_allocation_value

    if task_allocations_changeset:
        log.log(TRACE, '_calculate_task_allocations_changeset():'
                       '\ncurrent_task_allocations=\n%s'
                       '\nnew_task_allocations=\n%s'
                       '\ntarget_task_allocations=\n%s'
                       '\ntask_allocations_changeset=\n%s',
                       pformat(current_task_allocations),
                       pformat(new_task_allocations),
                       pformat(target_task_allocations),
                       pformat(task_allocations_changeset)
                )

    return target_task_allocations, task_allocations_changeset


@trace(log, verbose=False)
def _calculate_tasks_allocations_changeset(
        current_tasks_allocations: TasksAllocations, new_tasks_allocations: TasksAllocations) \
        -> Tuple[TasksAllocations, TasksAllocations]:
    """Return tasks allocations that need to be applied.
    Takes as input:
    1) current_tasks_allocations: currently applied allocations in the system,
    2) new_tasks_allocations: new to be applied allocations

    and outputs:
    1) target_tasks_allocations: the list of all allocations which will
        be applied in the system in next step:
       so it is a sum of inputs (if the are conflicting allocations
       in both inputs the value is taken from new_tasks_allocations).
    2) tasks_allocations_changeset: only allocations from
       new_tasks_allocations which are not contained already
       in current_tasks_allocations (set difference
       of input new_tasks_allocations and input current_tasks_allocations)
    """
    target_tasks_allocations: TasksAllocations = {}
    tasks_allocations_changeset: TasksAllocations = {}

    # check and merge & overwrite with old allocations
    for task_id, current_task_allocations in current_tasks_allocations.items():
        if task_id in new_tasks_allocations:
            new_task_allocations = new_tasks_allocations[task_id]
            target_task_allocations, changeset_task_allocations = \
                _calculate_task_allocations_changeset(current_task_allocations,
                                                      new_task_allocations)
            target_tasks_allocations[task_id] = target_task_allocations
            if changeset_task_allocations:
                tasks_allocations_changeset[task_id] = changeset_task_allocations
        else:
            target_tasks_allocations[task_id] = current_task_allocations

    # if there are any new_allocations on task level that yet not exists in old_allocations
    # then just add them to both list
    only_new_tasks_ids = set(new_tasks_allocations) - set(current_tasks_allocations)
    for only_new_task_id in only_new_tasks_ids:
        task_allocations = new_tasks_allocations[only_new_task_id]
        target_tasks_allocations[only_new_task_id] = task_allocations
        tasks_allocations_changeset[only_new_task_id] = task_allocations

    return target_tasks_allocations, tasks_allocations_changeset


def _parse_schemata_file_row(line: str) -> Dict[str, str]:
    """Parse RDTAllocation.l3 and RDTAllocation.mb strings based on
    https://elixir.bootlin.com/linux/latest/source/arch/x86/kernel/cpu/intel_rdt_ctrlmondata.c#lL206
    and return dict mapping and domain id to its configuration (value).
    Resource type (e.g. mb, l3) is dropped.

    Eg.
    mb:1=20;2=50 returns {'1':'20', '2':'50'}
    mb:xxx=20mbs;2=50b returns {'1':'20mbs', '2':'50b'}
    raises ValueError exception for inproper format or conflicting domains ids.
    """
    RESOURCE_ID_SEPARATOR = ':'
    DOMAIN_ID_SEPARATOR = ';'
    VALUE_SEPARATOR = '='

    domains = {}

    # Ignore emtpy line.
    if not line:
        return {}

    # Drop resource identifier prefix like ("mb:")
    line = line[line.find(RESOURCE_ID_SEPARATOR)+1:]
    # Domains
    domains_with_values = line.split(DOMAIN_ID_SEPARATOR)
    for domain_with_value in domains_with_values:
        if not domain_with_value:
            raise ValueError('domain cannot be empty')
        if VALUE_SEPARATOR not in domain_with_value:
            raise ValueError('Value separator is missing "="!')
        separator_position = domain_with_value.find(VALUE_SEPARATOR)
        domain_id = domain_with_value[:separator_position]
        if not domain_id:
            raise ValueError('domain_id cannot be empty!')
        value = domain_with_value[separator_position+1:]
        if not value:
            raise ValueError('value cannot be empty!')

        if domain_id in domains:
            raise ValueError('Conflicting domain id found!')

        domains[domain_id] = value

    return domains


def _count_enabled_bits(hexstr: str) -> int:
    """Parse a raw value like f202 to number of bits enabled."""
    if hexstr == '':
        return 0
    value_int = int(hexstr, 16)
    enabled_bits_count = bin(value_int).count('1')
    return enabled_bits_count