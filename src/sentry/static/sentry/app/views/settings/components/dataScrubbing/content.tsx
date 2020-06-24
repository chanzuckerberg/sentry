import React from 'react';

import {t} from 'app/locale';
import EmptyMessage from 'app/views/settings/components/emptyMessage';
import {IconWarning} from 'app/icons';

import RulesList from './rulesList';
import {Rule} from './types';

type Props = {
  rules: Array<Rule>;
  onEditRule: (rule: Rule['id']) => () => void;
  onDeleteRule: (rule: Rule['id']) => () => void;
  disabled?: boolean;
};

const Content = ({rules, disabled, onDeleteRule, onEditRule}: Props) => {
  if (rules.length === 0) {
    return (
      <EmptyMessage
        icon={<IconWarning size="xl" />}
        description={t('You have no data scrubbing rules')}
      />
    );
  }

  return (
    <RulesList
      rules={rules}
      onDeleteRule={onDeleteRule}
      onEditRule={onEditRule}
      disabled={disabled}
    />
  );
};

export default Content;
