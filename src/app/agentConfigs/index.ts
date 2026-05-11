import { callcenteragentScenario } from './callcenteragent';
import type { AgentOption } from './types';

export const allAgentSets: Record<string, AgentOption[]> = {
  callcenteragent: callcenteragentScenario,
};

export const defaultAgentSetKey = 'callcenteragent';
