"""Park pauses armed Ford lateral like the Neutral/Reverse transition; it never grants output."""
from types import SimpleNamespace

import pytest

from opendbc.car import structs
from opendbc.car.ford.values import CAR, FordFlags
from openpilot.selfdrive.selfdrived.selfdrived import SelfdriveD
from openpilot.starpilot.aol.tests.test_reverse_source_gap import NOW, PRODUCER, sample
from openpilot.starpilot.aol.transport_pause import TransportPauseFeedback
from openpilot.starpilot.car.ford.aol import park_pause


def ford_cp(alternative_experience=32):
  return structs.CarParams(brand='ford', carFingerprint=CAR.FORD_MUSTANG_MACH_E_MK1,
    flags=int(FordFlags.CANFD), alternativeExperience=alternative_experience, steerControlType='angle',
    transmissionType='automatic', pcmCruise=True,
    safetyConfigs=[structs.CarParams.SafetyConfig(safetyModel='ford', safetyParam=0x4002)])


def state(gear='park', **fields):
  cs = structs.CarState(canValid=True, gearShifter=gear, **fields)
  cs.cruiseState.available = True
  return cs


def gear_pause(cp, cs, samples):
  return SelfdriveD.aol_gear_pause(SimpleNamespace(CP=cp, car_state_samples=samples), cs)


@pytest.mark.parametrize('previous', ['drive', 'neutral', 'reverse', 'park'])
def test_ford_park_pauses_armed_lateral(previous):
  cp, cs = ford_cp(), state()
  samples = ((state(previous), True), (cs, True))
  assert park_pause(cp, cs, samples)
  assert gear_pause(cp, cs, samples)


@pytest.mark.parametrize('fault', ['drive', 'door', 'belt', 'can', 'timeout', 'invalid_sample', 'unknown_sample',
                                   'not_qualified', 'other_brand'])
def test_ford_park_pause_rejects_faults_and_other_brands(fault):
  cp, cs, previous, valid = ford_cp(), state(), state('drive'), True
  if fault == 'drive':
    cs = state('drive')
  elif fault == 'door':
    cs.doorOpen = True
  elif fault == 'belt':
    cs.seatbeltUnlatched = True
  elif fault == 'can':
    cs.canValid = False
  elif fault == 'timeout':
    cs.canTimeout = True
  elif fault == 'invalid_sample':
    valid = False
  elif fault == 'unknown_sample':
    previous = state('unknown')
  elif fault == 'not_qualified':
    cp = ford_cp(alternative_experience=0)
  elif fault == 'other_brand':
    cp.brand = 'hyundai'
  samples = ((previous, valid), (cs, True))
  assert not park_pause(cp, cs, samples)
  if fault != 'drive':
    assert not gear_pause(cp, cs, samples)


def test_neutral_and_reverse_keep_the_shared_pause():
  cp = ford_cp()
  for gear in ('neutral', 'reverse'):
    cs = state(gear)
    assert not park_pause(cp, cs, ((cs, True),))
    assert gear_pause(cp, cs, ((state('drive'), True), (cs, True)))


def test_ford_park_source_gap_retains_only_existing_inactive_intent():
  cp = ford_cp()
  cs = state('drive')
  feedback = TransportPauseFeedback(cp)
  active, _ = sample(cp, NOW - 10_000_000, active=True)
  assert not feedback.observe(active, cp, cs, NOW - 10_000_000, latched=True, intent_producer_session=PRODUCER)
  cs.gearShifter = 'reverse'
  off, _ = sample(cp, NOW, 2)
  assert not feedback.observe(off, cp, cs, NOW, latched=True, intent_producer_session=PRODUCER)
  cs.gearShifter = 'park'
  sm, _ = sample(cp, NOW + 32_000_000, 3, gap=True)
  before = dict(vars(feedback))
  assert not feedback.observe(sm, cp, cs, NOW + 32_000_000, latched=True, intent_producer_session=PRODUCER)
  assert vars(feedback) == before
  # The gap still cannot outlive the original 200ms intent bound.
  sm, _ = sample(cp, NOW + 200_000_001, 4, gap=True)
  assert feedback.observe(sm, cp, cs, NOW + 200_000_001, latched=True, intent_producer_session=PRODUCER)


def test_ford_park_source_gap_ends_when_the_door_opens():
  cp = ford_cp()
  cs = state('drive')
  feedback = TransportPauseFeedback(cp)
  active, _ = sample(cp, NOW - 10_000_000, active=True)
  assert not feedback.observe(active, cp, cs, NOW - 10_000_000, latched=True, intent_producer_session=PRODUCER)
  cs.gearShifter = 'reverse'
  off, _ = sample(cp, NOW, 2)
  assert not feedback.observe(off, cp, cs, NOW, latched=True, intent_producer_session=PRODUCER)
  cs.gearShifter = 'park'
  cs.doorOpen = True
  sm, _ = sample(cp, NOW + 32_000_000, 3, gap=True)
  assert feedback.observe(sm, cp, cs, NOW + 32_000_000, latched=True, intent_producer_session=PRODUCER)
