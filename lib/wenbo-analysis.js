(function (root) {
  'use strict';

  function parseDate(value) {
    var parts = String(value || '').slice(0, 10).split('-');
    if (parts.length !== 3) return NaN;
    return Date.UTC(+parts[0], +parts[1] - 1, +parts[2]);
  }

  function dateKey(value) {
    var d = new Date(value);
    return d.getUTCFullYear() + '-' + String(d.getUTCMonth() + 1).padStart(2, '0') + '-' + String(d.getUTCDate()).padStart(2, '0');
  }

  function daysBetween(start, end) {
    return Math.max(0, Math.round((parseDate(end) - parseDate(start)) / 86400000));
  }

  function eventInRange(event, asOf, days, previous) {
    var age = daysBetween(event.lastDate, asOf);
    var from = previous ? days : 0;
    var to = previous ? days * 2 : days;
    return age >= from && age < to;
  }

  function eventScore(event, asOf, decay) {
    var age = daysBetween(event.lastDate, asOf);
    var recency = 100 * Math.pow(decay || 0.93, age);
    return (+event.impact || 0) * 0.35 + (+event.evidence || 0) * 0.30 +
      (+event.breadth || 0) * 0.20 + recency * 0.15;
  }

  function provinceRows(events, options) {
    options = options || {};
    var byName = {};
    (events || []).forEach(function (event) {
      if (!eventInRange(event, options.asOf, options.days, options.previous)) return;
      if (options.theme && (event.themes || []).indexOf(options.theme) === -1) return;
      if (!event.primaryProvince) return;
      var name = event.primaryProvince;
      if (!byName[name]) {
        byName[name] = {name:name, raw:0, eventCount:0, reportCount:0, evidenceCount:0, aCount:0, confidenceTotal:0, events:[]};
      }
      var score = eventScore(event, options.asOf, options.decay);
      var row = byName[name];
      row.raw += score;
      row.eventCount += 1;
      row.reportCount += event.reportCount || 0;
      row.evidenceCount += event.sourceCount || 0;
      row.aCount += event.sourceTier === 'A' ? 1 : 0;
      row.confidenceTotal += event.locationConfidence || 0;
      row.events.push({event:event, score:score});
    });
    var rows = Object.keys(byName).map(function (key) { return byName[key]; });
    var maxRaw = rows.reduce(function (max, row) { return Math.max(max, row.raw); }, 0);
    rows.forEach(function (row) {
      row.index = maxRaw ? row.raw / maxRaw * 100 : 0;
      row.confidence = row.eventCount ? row.confidenceTotal / row.eventCount : 0;
      row.events.sort(function (a, b) { return b.score - a.score; });
    });
    return rows.sort(function (a, b) { return b.raw - a.raw; });
  }

  function coverageForWindow(coverage, asOf, days, previous, mode, runType) {
    coverage = coverage || {};
    var panel = coverage.panel || [], checks = (coverage.checks || []).filter(function (row) {
      return (!mode || row.mode === mode) && (!runType || row.runType === runType);
    });
    var good = {success:true, no_update:true};
    var start = previous ? days : 0;
    var byKey = {}, sourceRows = {};
    var statusRank = {no_update:1, success:2, partial:3, failed:4};
    function checkedAt(row) { return Date.parse(row.checkedAt || row.checked_at || row.timestamp || row.updatedAt || '') || 0; }
    function shouldReplace(oldRow, newRow) {
      if (!oldRow) return true;
      var oldTime = checkedAt(oldRow), newTime = checkedAt(newRow);
      if (oldTime !== newTime) return newTime > oldTime;
      return (statusRank[newRow.status] || 0) > (statusRank[oldRow.status] || 0);
    }
    panel.forEach(function (source) {
      sourceRows[source.id] = {id:source.id, name:source.name, role:source.role, good:0, success:0, noUpdate:0, partial:0, failed:0, checks:0, latest:'', actualStart:'', actualEnd:''};
    });
    checks.forEach(function (row) {
      if (!sourceRows[row.sourceId]) return;
      var age = daysBetween(row.date, asOf);
      if (age < start || age >= start + days) return;
      var key = row.date + '|' + row.sourceId;
      if (shouldReplace(byKey[key], row)) byKey[key] = row;
    });
    Object.keys(byKey).forEach(function (key) {
      var row = byKey[key];
      var source = sourceRows[row.sourceId];
      source.checks += 1;
      source.actualStart = !source.actualStart || row.date < source.actualStart ? row.date : source.actualStart;
      source.actualEnd = !source.actualEnd || row.date > source.actualEnd ? row.date : source.actualEnd;
      if (!source.latest || row.date > source.latest) { source.latest = row.date; source.latestStatus = row.status; }
      if (good[row.status]) source.good += 1;
      if (row.status === 'success') source.success += 1;
      if (row.status === 'no_update') source.noUpdate += 1;
      if (row.status === 'partial') source.partial += 1;
      if (row.status === 'failed') source.failed += 1;
    });
    var completeDays = 0;
    for (var i = 0; i < days; i++) {
      var day = dateKey(parseDate(asOf) - (start + i) * 86400000);
      var complete = panel.length > 0;
      panel.forEach(function (source) {
        var row = byKey[day + '|' + source.id];
        if (!row || !good[row.status]) complete = false;
      });
      if (complete) completeDays += 1;
    }
    var rows = panel.map(function (source) {
      var row = sourceRows[source.id];
      if (row.failed || (!row.checks && mode !== 'operational')) row.state = 'failed';
      else if (!row.checks && mode === 'operational') row.state = 'not_started';
      else if (row.partial || row.good < days) row.state = 'partial';
      else if (!row.success && row.noUpdate) row.state = 'no_update';
      else row.state = 'complete';
      return row;
    });
    var successful = rows.reduce(function (sum, row) { return sum + row.good; }, 0);
    var planned = panel.length * days;
    var rate = planned ? successful / planned : 0;
    var failed = rows.some(function (row) { return row.state === 'failed'; });
    var hasChecks = Object.keys(byKey).length > 0;
    return {
      panel:panel, rows:rows, byKey:byKey, completeDays:completeDays,
      successful:successful, planned:planned, rate:rate,
      effectiveSources:rows.filter(function (row) { return row.good > 0; }).length,
      state:failed ? 'failed' : (!hasChecks ? 'insufficient' : (rate >= 0.90 && completeDays >= Math.ceil(days * 0.80) ? 'ready' : (rate >= 0.60 ? 'partial' : 'insufficient'))),
      start:dateKey(parseDate(asOf) - (start + days - 1) * 86400000), end:dateKey(parseDate(asOf) - start * 86400000)
    };
  }

  function aggregateArticles(items) {
    var byUrl = {};
    (items || []).forEach(function (item) {
      var key = item.u || item.url || ((item.t || item.title || '') + '|' + (item.d || item.date || ''));
      if (!key) return;
      var date = item.d || item.date || '';
      if (!byUrl[key]) {
        byUrl[key] = {u:item.u || item.url || '', t:item.t || item.title || '', d:date, l:item.l || item.level || '', topics:[], matchedKeywords:[], excerpts:[], recordCount:0};
      }
      var article = byUrl[key];
      article.recordCount += 1;
      if (date && (!article.d || date < article.d)) { article.d = date; article.t = item.t || item.title || article.t; article.l = item.l || item.level || article.l; }
      (item.topics || []).forEach(function (topic) { if (article.topics.indexOf(topic) === -1) article.topics.push(topic); });
      var keyword = item.w || item.word;
      if (keyword && article.matchedKeywords.indexOf(keyword) === -1) article.matchedKeywords.push(keyword);
      var excerpt = item.t || item.title || '';
      if (excerpt && article.excerpts.indexOf(excerpt) === -1) article.excerpts.push(excerpt);
    });
    return Object.keys(byUrl).map(function (key) { return byUrl[key]; }).sort(function (a, b) { return parseDate(b.d) - parseDate(a.d); });
  }

  root.WenboAnalysis = {
    parseDate:parseDate,
    dateKey:dateKey,
    daysBetween:daysBetween,
    eventInRange:eventInRange,
    eventScore:eventScore,
    provinceRows:provinceRows,
    coverageForWindow:coverageForWindow,
    aggregateArticles:aggregateArticles
  };
})(window);
