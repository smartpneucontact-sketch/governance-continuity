import os
import json
from datetime import datetime, timedelta
from flask import Flask, render_template, request, redirect, url_for, flash, jsonify
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
from werkzeug.security import generate_password_hash, check_password_hash

app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'gca-dev-key-change-me')
app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get('DATABASE_URL', 'sqlite:///governance.db')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

if app.config['SQLALCHEMY_DATABASE_URI'].startswith('postgres://'):
    app.config['SQLALCHEMY_DATABASE_URI'] = app.config['SQLALCHEMY_DATABASE_URI'].replace('postgres://', 'postgresql://', 1)

db = SQLAlchemy(app)
login_manager = LoginManager(app)
login_manager.login_view = 'login'

# ─── Models ────────────────────────────────────────────────────────────────────

class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(256), nullable=False)
    name = db.Column(db.String(100), nullable=False)
    role = db.Column(db.String(50), default='member')
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)


class AuthorityRole(db.Model):
    """Role-Based Authority Registry — authority is encoded to ROLES, not persons."""
    id = db.Column(db.Integer, primary_key=True)
    role_title = db.Column(db.String(150), nullable=False)
    department = db.Column(db.String(100), nullable=False)
    authority_scope = db.Column(db.Text, nullable=True)  # What this role can decide
    current_holder_name = db.Column(db.String(100), nullable=True)
    current_holder_email = db.Column(db.String(120), nullable=True)
    status = db.Column(db.String(30), default='active')  # active, disrupted, vacant, transitioning
    disruption_type = db.Column(db.String(50), nullable=True)
    disruption_start = db.Column(db.DateTime, nullable=True)
    expected_return = db.Column(db.DateTime, nullable=True)
    successor_role_id = db.Column(db.Integer, db.ForeignKey('authority_role.id'), nullable=True)
    backup_role_id = db.Column(db.Integer, db.ForeignKey('authority_role.id'), nullable=True)
    notes = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    successor_role = db.relationship('AuthorityRole', remote_side=[id], foreign_keys=[successor_role_id],
                                     backref='primary_successor_for')
    backup_role = db.relationship('AuthorityRole', remote_side=[id], foreign_keys=[backup_role_id],
                                  backref='backup_for')


class DecisionDomain(db.Model):
    """Decision Continuity Framework — domains persist regardless of who holds the role."""
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(150), nullable=False)
    description = db.Column(db.Text, nullable=True)
    category = db.Column(db.String(50), default='operational')  # strategic, operational, compliance, financial
    authority_role_id = db.Column(db.Integer, db.ForeignKey('authority_role.id'), nullable=True)
    ai_support_level = db.Column(db.String(30), default='none')  # none, advisory, assisted, autonomous
    ai_boundary_notes = db.Column(db.Text, nullable=True)
    human_judgment_required = db.Column(db.Boolean, default=True)
    risk_level = db.Column(db.String(20), default='medium')
    decision_velocity = db.Column(db.String(20), default='normal')  # fast, normal, slow, stalled
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    authority_role = db.relationship('AuthorityRole', backref='decision_domains')


class EscalationPath(db.Model):
    """AI-Assisted Escalation Maps — what happens when authority is unclear."""
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(150), nullable=False)
    trigger_condition = db.Column(db.Text, nullable=False)  # When does this escalation fire?
    domain_id = db.Column(db.Integer, db.ForeignKey('decision_domain.id'), nullable=True)
    step1_role_id = db.Column(db.Integer, db.ForeignKey('authority_role.id'), nullable=True)
    step2_role_id = db.Column(db.Integer, db.ForeignKey('authority_role.id'), nullable=True)
    step3_role_id = db.Column(db.Integer, db.ForeignKey('authority_role.id'), nullable=True)
    ai_can_auto_escalate = db.Column(db.Boolean, default=False)
    max_wait_hours = db.Column(db.Integer, default=24)
    fallback_action = db.Column(db.Text, nullable=True)  # What happens if nobody is available
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    domain = db.relationship('DecisionDomain', backref='escalation_paths')
    step1_role = db.relationship('AuthorityRole', foreign_keys=[step1_role_id])
    step2_role = db.relationship('AuthorityRole', foreign_keys=[step2_role_id])
    step3_role = db.relationship('AuthorityRole', foreign_keys=[step3_role_id])


class GovernanceSignal(db.Model):
    """Governance Signal Monitoring — detect governance stress before it becomes a crisis."""
    id = db.Column(db.Integer, primary_key=True)
    signal_type = db.Column(db.String(50), nullable=False)
    # types: decision_stall, authority_gap, escalation_failure, overload, trust_erosion, velocity_drop
    severity = db.Column(db.String(20), default='warning')  # info, warning, critical
    title = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text, nullable=True)
    related_role_id = db.Column(db.Integer, db.ForeignKey('authority_role.id'), nullable=True)
    related_domain_id = db.Column(db.Integer, db.ForeignKey('decision_domain.id'), nullable=True)
    status = db.Column(db.String(20), default='active')  # active, acknowledged, resolved
    detected_at = db.Column(db.DateTime, default=datetime.utcnow)
    resolved_at = db.Column(db.DateTime, nullable=True)

    related_role = db.relationship('AuthorityRole', backref='signals')
    related_domain = db.relationship('DecisionDomain', backref='signals')


class DisruptionEvent(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    role_id = db.Column(db.Integer, db.ForeignKey('authority_role.id'), nullable=False)
    event_type = db.Column(db.String(50), nullable=False)
    description = db.Column(db.Text, nullable=True)
    started_at = db.Column(db.DateTime, default=datetime.utcnow)
    resolved_at = db.Column(db.DateTime, nullable=True)
    interim_role_id = db.Column(db.Integer, db.ForeignKey('authority_role.id'), nullable=True)
    impact_assessment = db.Column(db.Text, nullable=True)
    actions_taken = db.Column(db.Text, nullable=True)
    affected_domains_count = db.Column(db.Integer, default=0)
    status = db.Column(db.String(20), default='active')

    role = db.relationship('AuthorityRole', foreign_keys=[role_id], backref='disruption_events')
    interim_role = db.relationship('AuthorityRole', foreign_keys=[interim_role_id])


class GovernanceLog(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    action = db.Column(db.String(200), nullable=False)
    details = db.Column(db.Text, nullable=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    user = db.relationship('User', backref='logs')


@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))


# ─── Routes ────────────────────────────────────────────────────────────────────

@app.route('/')
def index():
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))
    return render_template('landing.html')


@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        email = request.form['email']
        name = request.form['name']
        password = request.form['password']
        if User.query.filter_by(email=email).first():
            flash('Email already registered.', 'error')
            return redirect(url_for('register'))
        user = User(email=email, name=name, role='admin')
        user.set_password(password)
        db.session.add(user)
        db.session.commit()
        log_action(f'User registered: {name}', user_id=user.id)
        login_user(user)
        flash('Account created. Welcome to the Governance Continuity Architecture.', 'success')
        return redirect(url_for('dashboard'))
    return render_template('register.html')


@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        user = User.query.filter_by(email=request.form['email']).first()
        if user and user.check_password(request.form['password']):
            login_user(user)
            return redirect(url_for('dashboard'))
        flash('Invalid credentials.', 'error')
    return render_template('login.html')


@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('index'))


@app.route('/dashboard')
@login_required
def dashboard():
    roles = AuthorityRole.query.all()
    domains = DecisionDomain.query.all()
    active_disruptions = DisruptionEvent.query.filter_by(status='active').all()
    active_signals = GovernanceSignal.query.filter_by(status='active').order_by(GovernanceSignal.severity.desc()).all()
    recent_logs = GovernanceLog.query.order_by(GovernanceLog.created_at.desc()).limit(8).all()
    escalations = EscalationPath.query.all()

    stats = {
        'total_roles': len(roles),
        'active_roles': sum(1 for r in roles if r.status == 'active'),
        'disrupted_roles': sum(1 for r in roles if r.status == 'disrupted'),
        'vacant_roles': sum(1 for r in roles if r.status == 'vacant'),
        'total_domains': len(domains),
        'unassigned_domains': sum(1 for d in domains if not d.authority_role_id),
        'stalled_domains': sum(1 for d in domains if d.decision_velocity == 'stalled'),
        'ai_governed': sum(1 for d in domains if d.ai_support_level != 'none'),
        'critical_domains': sum(1 for d in domains if d.risk_level == 'critical'),
        'active_disruptions': len(active_disruptions),
        'active_signals': len(active_signals),
        'critical_signals': sum(1 for s in active_signals if s.severity == 'critical'),
        'escalation_paths': len(escalations),
        'roles_with_succession': sum(1 for r in roles if r.successor_role_id),
    }

    # Governance Continuity Score — weighted across architecture dimensions
    if stats['total_roles'] > 0:
        role_coverage = stats['active_roles'] / stats['total_roles']
    else:
        role_coverage = 1.0
    if stats['total_domains'] > 0:
        domain_coverage = (stats['total_domains'] - stats['unassigned_domains']) / stats['total_domains']
    else:
        domain_coverage = 1.0
    succession_depth = stats['roles_with_succession'] / max(len(roles), 1)
    escalation_coverage = min(len(escalations) / max(stats['critical_domains'], 1), 1.0)
    signal_health = max(0, 1 - (stats['critical_signals'] * 0.25))

    stats['continuity_score'] = int(
        role_coverage * 25 +
        domain_coverage * 25 +
        succession_depth * 20 +
        escalation_coverage * 15 +
        signal_health * 15
    )

    # Decision velocity breakdown
    velocity = {'fast': 0, 'normal': 0, 'slow': 0, 'stalled': 0}
    for d in domains:
        velocity[d.decision_velocity] = velocity.get(d.decision_velocity, 0) + 1
    stats['velocity'] = velocity

    return render_template('dashboard.html', stats=stats, roles=roles,
                           active_disruptions=active_disruptions, active_signals=active_signals,
                           recent_logs=recent_logs)


# ─── Authority Registry ───────────────────────────────────────────────────────

@app.route('/registry')
@login_required
def registry():
    roles = AuthorityRole.query.order_by(AuthorityRole.department, AuthorityRole.role_title).all()
    return render_template('registry.html', roles=roles)


@app.route('/registry/add', methods=['GET', 'POST'])
@login_required
def add_role():
    if request.method == 'POST':
        role = AuthorityRole(
            role_title=request.form['role_title'],
            department=request.form['department'],
            authority_scope=request.form.get('authority_scope', ''),
            current_holder_name=request.form.get('current_holder_name', ''),
            current_holder_email=request.form.get('current_holder_email', ''),
            status='active',
        )
        succ = request.form.get('successor_role_id')
        if succ:
            role.successor_role_id = int(succ)
        backup = request.form.get('backup_role_id')
        if backup:
            role.backup_role_id = int(backup)
        db.session.add(role)
        db.session.commit()
        log_action(f'Authority role registered: {role.role_title}')
        flash('Authority role added to registry.', 'success')
        return redirect(url_for('registry'))
    all_roles = AuthorityRole.query.order_by(AuthorityRole.role_title).all()
    return render_template('role_form.html', role=None, all_roles=all_roles)


@app.route('/registry/<int:id>/edit', methods=['GET', 'POST'])
@login_required
def edit_role(id):
    role = AuthorityRole.query.get_or_404(id)
    if request.method == 'POST':
        role.role_title = request.form['role_title']
        role.department = request.form['department']
        role.authority_scope = request.form.get('authority_scope', '')
        role.current_holder_name = request.form.get('current_holder_name', '')
        role.current_holder_email = request.form.get('current_holder_email', '')
        role.notes = request.form.get('notes', '')
        succ = request.form.get('successor_role_id')
        role.successor_role_id = int(succ) if succ else None
        backup = request.form.get('backup_role_id')
        role.backup_role_id = int(backup) if backup else None
        db.session.commit()
        log_action(f'Authority role updated: {role.role_title}')
        flash('Role updated.', 'success')
        return redirect(url_for('registry'))
    all_roles = AuthorityRole.query.filter(AuthorityRole.id != id).order_by(AuthorityRole.role_title).all()
    return render_template('role_form.html', role=role, all_roles=all_roles)


@app.route('/registry/<int:id>/disrupt', methods=['GET', 'POST'])
@login_required
def disrupt_role(id):
    role = AuthorityRole.query.get_or_404(id)
    if request.method == 'POST':
        role.status = 'disrupted'
        role.disruption_type = request.form['disruption_type']
        role.disruption_start = datetime.utcnow()
        exp_return = request.form.get('expected_return')
        if exp_return:
            role.expected_return = datetime.strptime(exp_return, '%Y-%m-%d')

        affected = DecisionDomain.query.filter_by(authority_role_id=role.id).count()

        event = DisruptionEvent(
            role_id=role.id,
            event_type=request.form['disruption_type'],
            description=request.form.get('description', ''),
            interim_role_id=role.successor_role_id,
            affected_domains_count=affected,
            status='active',
        )
        db.session.add(event)

        # Auto-generate governance signals
        if affected > 0:
            signal = GovernanceSignal(
                signal_type='authority_gap',
                severity='critical' if affected >= 3 else 'warning',
                title=f'Authority gap: {role.role_title} disrupted — {affected} domain(s) affected',
                description=f'{role.current_holder_name or "Holder"} unavailable ({role.disruption_type}). '
                            f'{affected} decision domain(s) require interim authority.',
                related_role_id=role.id,
                status='active',
            )
            db.session.add(signal)

        # Check for stalled decision velocity
        for domain in role.decision_domains:
            if domain.risk_level in ('critical', 'high'):
                domain.decision_velocity = 'stalled'
                stall_signal = GovernanceSignal(
                    signal_type='decision_stall',
                    severity='critical',
                    title=f'Decision stall: {domain.name}',
                    description=f'Authority holder disrupted. {domain.name} decisions may be paralyzed.',
                    related_role_id=role.id,
                    related_domain_id=domain.id,
                    status='active',
                )
                db.session.add(stall_signal)

        db.session.commit()
        log_action(f'Disruption recorded: {role.role_title} — {role.disruption_type} ({affected} domains affected)')
        flash(f'Disruption recorded for {role.role_title}. {affected} domain(s) affected.', 'warning')
        return redirect(url_for('registry'))
    return render_template('disrupt_form.html', role=role)


@app.route('/registry/<int:id>/restore', methods=['POST'])
@login_required
def restore_role(id):
    role = AuthorityRole.query.get_or_404(id)
    role.status = 'active'
    role.disruption_type = None
    role.disruption_start = None
    role.expected_return = None
    for event in role.disruption_events:
        if event.status == 'active':
            event.status = 'resolved'
            event.resolved_at = datetime.utcnow()
    # Resolve related signals
    for signal in role.signals:
        if signal.status == 'active':
            signal.status = 'resolved'
            signal.resolved_at = datetime.utcnow()
    # Restore decision velocity
    for domain in role.decision_domains:
        if domain.decision_velocity == 'stalled':
            domain.decision_velocity = 'normal'
    db.session.commit()
    log_action(f'Authority restored: {role.role_title}')
    flash(f'{role.role_title} restored to active status.', 'success')
    return redirect(url_for('registry'))


@app.route('/registry/<int:id>/delete', methods=['POST'])
@login_required
def delete_role(id):
    role = AuthorityRole.query.get_or_404(id)
    title = role.role_title
    for r in AuthorityRole.query.filter_by(successor_role_id=id).all():
        r.successor_role_id = None
    for r in AuthorityRole.query.filter_by(backup_role_id=id).all():
        r.backup_role_id = None
    for d in DecisionDomain.query.filter_by(authority_role_id=id).all():
        d.authority_role_id = None
    db.session.delete(role)
    db.session.commit()
    log_action(f'Authority role removed: {title}')
    flash(f'{title} removed.', 'success')
    return redirect(url_for('registry'))


# ─── Decision Domains ─────────────────────────────────────────────────────────

@app.route('/domains')
@login_required
def domains_list():
    domains = DecisionDomain.query.order_by(DecisionDomain.category, DecisionDomain.name).all()
    return render_template('domains.html', domains=domains)


@app.route('/domains/add', methods=['GET', 'POST'])
@login_required
def add_domain():
    if request.method == 'POST':
        domain = DecisionDomain(
            name=request.form['name'],
            description=request.form.get('description', ''),
            category=request.form['category'],
            risk_level=request.form['risk_level'],
            ai_support_level=request.form['ai_support_level'],
            ai_boundary_notes=request.form.get('ai_boundary_notes', ''),
            human_judgment_required='human_judgment_required' in request.form,
            decision_velocity=request.form.get('decision_velocity', 'normal'),
        )
        role_id = request.form.get('authority_role_id')
        if role_id:
            domain.authority_role_id = int(role_id)
        db.session.add(domain)
        db.session.commit()
        log_action(f'Decision domain added: {domain.name}')
        flash('Decision domain added.', 'success')
        return redirect(url_for('domains_list'))
    roles = AuthorityRole.query.order_by(AuthorityRole.role_title).all()
    return render_template('domain_form.html', domain=None, roles=roles)


@app.route('/domains/<int:id>/edit', methods=['GET', 'POST'])
@login_required
def edit_domain(id):
    domain = DecisionDomain.query.get_or_404(id)
    if request.method == 'POST':
        domain.name = request.form['name']
        domain.description = request.form.get('description', '')
        domain.category = request.form['category']
        domain.risk_level = request.form['risk_level']
        domain.ai_support_level = request.form['ai_support_level']
        domain.ai_boundary_notes = request.form.get('ai_boundary_notes', '')
        domain.human_judgment_required = 'human_judgment_required' in request.form
        domain.decision_velocity = request.form.get('decision_velocity', 'normal')
        role_id = request.form.get('authority_role_id')
        domain.authority_role_id = int(role_id) if role_id else None
        db.session.commit()
        log_action(f'Decision domain updated: {domain.name}')
        flash('Domain updated.', 'success')
        return redirect(url_for('domains_list'))
    roles = AuthorityRole.query.order_by(AuthorityRole.role_title).all()
    return render_template('domain_form.html', domain=domain, roles=roles)


@app.route('/domains/<int:id>/delete', methods=['POST'])
@login_required
def delete_domain(id):
    domain = DecisionDomain.query.get_or_404(id)
    name = domain.name
    db.session.delete(domain)
    db.session.commit()
    log_action(f'Decision domain deleted: {name}')
    flash(f'{name} removed.', 'success')
    return redirect(url_for('domains_list'))


# ─── Escalation Maps ──────────────────────────────────────────────────────────

@app.route('/escalations')
@login_required
def escalations_list():
    escalations = EscalationPath.query.order_by(EscalationPath.name).all()
    return render_template('escalations.html', escalations=escalations)


@app.route('/escalations/add', methods=['GET', 'POST'])
@login_required
def add_escalation():
    if request.method == 'POST':
        esc = EscalationPath(
            name=request.form['name'],
            trigger_condition=request.form['trigger_condition'],
            ai_can_auto_escalate='ai_can_auto_escalate' in request.form,
            max_wait_hours=int(request.form.get('max_wait_hours', 24)),
            fallback_action=request.form.get('fallback_action', ''),
        )
        for field, attr in [('domain_id', 'domain_id'), ('step1_role_id', 'step1_role_id'),
                            ('step2_role_id', 'step2_role_id'), ('step3_role_id', 'step3_role_id')]:
            val = request.form.get(field)
            if val:
                setattr(esc, attr, int(val))
        db.session.add(esc)
        db.session.commit()
        log_action(f'Escalation path created: {esc.name}')
        flash('Escalation path created.', 'success')
        return redirect(url_for('escalations_list'))
    roles = AuthorityRole.query.order_by(AuthorityRole.role_title).all()
    domains = DecisionDomain.query.order_by(DecisionDomain.name).all()
    return render_template('escalation_form.html', esc=None, roles=roles, domains=domains)


@app.route('/escalations/<int:id>/edit', methods=['GET', 'POST'])
@login_required
def edit_escalation(id):
    esc = EscalationPath.query.get_or_404(id)
    if request.method == 'POST':
        esc.name = request.form['name']
        esc.trigger_condition = request.form['trigger_condition']
        esc.ai_can_auto_escalate = 'ai_can_auto_escalate' in request.form
        esc.max_wait_hours = int(request.form.get('max_wait_hours', 24))
        esc.fallback_action = request.form.get('fallback_action', '')
        for field, attr in [('domain_id', 'domain_id'), ('step1_role_id', 'step1_role_id'),
                            ('step2_role_id', 'step2_role_id'), ('step3_role_id', 'step3_role_id')]:
            val = request.form.get(field)
            setattr(esc, attr, int(val) if val else None)
        db.session.commit()
        log_action(f'Escalation path updated: {esc.name}')
        flash('Escalation path updated.', 'success')
        return redirect(url_for('escalations_list'))
    roles = AuthorityRole.query.order_by(AuthorityRole.role_title).all()
    domains = DecisionDomain.query.order_by(DecisionDomain.name).all()
    return render_template('escalation_form.html', esc=esc, roles=roles, domains=domains)


@app.route('/escalations/<int:id>/delete', methods=['POST'])
@login_required
def delete_escalation(id):
    esc = EscalationPath.query.get_or_404(id)
    name = esc.name
    db.session.delete(esc)
    db.session.commit()
    log_action(f'Escalation path deleted: {name}')
    flash(f'{name} removed.', 'success')
    return redirect(url_for('escalations_list'))


# ─── Governance Signals ────────────────────────────────────────────────────────

@app.route('/signals')
@login_required
def signals_list():
    signals = GovernanceSignal.query.order_by(
        GovernanceSignal.status.asc(),
        GovernanceSignal.severity.desc(),
        GovernanceSignal.detected_at.desc()
    ).all()
    return render_template('signals.html', signals=signals)


@app.route('/signals/<int:id>/acknowledge', methods=['POST'])
@login_required
def acknowledge_signal(id):
    signal = GovernanceSignal.query.get_or_404(id)
    signal.status = 'acknowledged'
    db.session.commit()
    log_action(f'Signal acknowledged: {signal.title}')
    flash('Signal acknowledged.', 'success')
    return redirect(url_for('signals_list'))


@app.route('/signals/<int:id>/resolve', methods=['POST'])
@login_required
def resolve_signal(id):
    signal = GovernanceSignal.query.get_or_404(id)
    signal.status = 'resolved'
    signal.resolved_at = datetime.utcnow()
    db.session.commit()
    log_action(f'Signal resolved: {signal.title}')
    flash('Signal resolved.', 'success')
    return redirect(url_for('signals_list'))


# ─── Disruption Events ────────────────────────────────────────────────────────

@app.route('/disruptions')
@login_required
def disruptions_list():
    events = DisruptionEvent.query.order_by(DisruptionEvent.started_at.desc()).all()
    return render_template('disruptions.html', events=events)


@app.route('/disruptions/<int:id>/update', methods=['POST'])
@login_required
def update_disruption(id):
    event = DisruptionEvent.query.get_or_404(id)
    event.actions_taken = request.form.get('actions_taken', event.actions_taken)
    event.impact_assessment = request.form.get('impact_assessment', event.impact_assessment)
    new_status = request.form.get('status', event.status)
    if new_status == 'resolved' and event.status != 'resolved':
        event.resolved_at = datetime.utcnow()
    event.status = new_status
    db.session.commit()
    log_action(f'Disruption event updated: {event.role.role_title} — {event.status}')
    flash('Disruption event updated.', 'success')
    return redirect(url_for('disruptions_list'))


# ─── AI Governance Matrix ──────────────────────────────────────────────────────

@app.route('/ai-matrix')
@login_required
def ai_matrix():
    domains = DecisionDomain.query.order_by(DecisionDomain.risk_level.desc(), DecisionDomain.name).all()
    return render_template('ai_matrix.html', domains=domains)


# ─── Audit Log ─────────────────────────────────────────────────────────────────

@app.route('/audit-log')
@login_required
def audit_log():
    logs = GovernanceLog.query.order_by(GovernanceLog.created_at.desc()).limit(100).all()
    return render_template('audit_log.html', logs=logs)


# ─── Helpers ───────────────────────────────────────────────────────────────────

def log_action(action, details=None, user_id=None):
    if user_id is None and current_user and current_user.is_authenticated:
        user_id = current_user.id
    entry = GovernanceLog(action=action, details=details, user_id=user_id)
    db.session.add(entry)
    db.session.commit()


def seed_demo_data():
    if AuthorityRole.query.count() > 0:
        return

    # ── Authority Roles (role-encoded, not person-bound) ──
    roles_data = [
        ('Chief Operating Officer', 'Operations', 'Enterprise-wide operational decisions, resource allocation, cross-functional coordination', 'Elena Vasquez', 'active'),
        ('VP of Engineering', 'Engineering', 'Technical architecture decisions, engineering resource allocation, build/buy decisions', 'James Chen', 'active'),
        ('Chief Compliance Officer', 'Legal & Compliance', 'Regulatory compliance decisions, audit responses, policy enforcement', 'Sarah Okafor', 'active'),
        ('VP of Product', 'Product', 'Product roadmap authority, feature prioritization, market positioning', 'Marcus Weber', 'disrupted'),
        ('Director of AI Strategy', 'Technology', 'AI deployment decisions, model governance, AI ethics review', 'Priya Sharma', 'active'),
        ('Chief Financial Officer', 'Finance', 'Budget authority, financial reporting, capital allocation', 'David Kim', 'active'),
        ('Head of People Ops', 'Human Resources', 'Hiring authority, compensation decisions, organizational design', 'Aisha Johnson', 'active'),
        ('Chief Technology Officer', 'Technology', 'Technology strategy, infrastructure decisions, security architecture', 'Robert Tanaka', 'transitioning'),
    ]

    created_roles = []
    for title, dept, scope, holder, status in roles_data:
        r = AuthorityRole(role_title=title, department=dept, authority_scope=scope,
                          current_holder_name=holder, status=status)
        if status == 'disrupted':
            r.disruption_type = 'medical'
            r.disruption_start = datetime.utcnow() - timedelta(days=12)
            r.expected_return = datetime.utcnow() + timedelta(days=18)
        elif status == 'transitioning':
            r.disruption_type = 'exit'
            r.disruption_start = datetime.utcnow() - timedelta(days=5)
        db.session.add(r)
        created_roles.append(r)

    db.session.flush()

    # Succession chains
    created_roles[3].successor_role_id = created_roles[4].id  # VP Product → Dir AI Strategy
    created_roles[7].successor_role_id = created_roles[1].id  # CTO → VP Engineering
    created_roles[0].successor_role_id = created_roles[5].id  # COO → CFO
    created_roles[1].backup_role_id = created_roles[4].id     # VP Eng backup → Dir AI

    # ── Decision Domains ──
    domains_data = [
        ('Annual Budget Approval', 'Final approval of organizational budget and capital allocation', 'financial', 'critical', 5, 'advisory', True, 'normal'),
        ('AI Model Deployment', 'Approval to deploy AI models into production environments', 'compliance', 'critical', 4, 'assisted', True, 'normal'),
        ('Vendor Selection', 'Selection and approval of technology and service vendors', 'operational', 'high', 0, 'advisory', True, 'normal'),
        ('Sprint Planning', 'Engineering sprint priorities and resource allocation', 'operational', 'medium', 1, 'assisted', False, 'fast'),
        ('Data Privacy Compliance', 'GDPR/CCPA compliance decisions and policy interpretation', 'compliance', 'critical', 2, 'advisory', True, 'normal'),
        ('Hiring Decisions', 'Final approval on new hires and role creation', 'operational', 'medium', 6, 'none', True, 'normal'),
        ('Incident Response', 'Production incident escalation and resolution authority', 'operational', 'high', 1, 'assisted', True, 'fast'),
        ('Product Roadmap', 'Quarterly product direction and feature prioritization', 'strategic', 'high', 3, 'advisory', True, 'stalled'),
        ('Customer Escalation', 'Executive-level customer issue resolution', 'operational', 'medium', 0, 'advisory', False, 'slow'),
        ('AI Ethics Review', 'Review of AI use cases for ethical alignment and bias assessment', 'compliance', 'critical', 4, 'none', True, 'normal'),
    ]

    created_domains = []
    for name, desc, cat, risk, role_idx, ai_level, human_req, velocity in domains_data:
        d = DecisionDomain(
            name=name, description=desc, category=cat, risk_level=risk,
            ai_support_level=ai_level, human_judgment_required=human_req,
            decision_velocity=velocity,
        )
        if role_idx > 0:
            d.authority_role_id = created_roles[role_idx].id
        db.session.add(d)
        created_domains.append(d)

    db.session.flush()

    # ── Escalation Paths ──
    esc1 = EscalationPath(
        name='Critical Compliance Escalation',
        trigger_condition='Compliance decision needed but CCO unavailable or authority unclear',
        domain_id=created_domains[4].id,
        step1_role_id=created_roles[2].id,  # CCO
        step2_role_id=created_roles[0].id,  # COO
        step3_role_id=created_roles[5].id,  # CFO
        ai_can_auto_escalate=True,
        max_wait_hours=4,
        fallback_action='Invoke regulatory hold — pause affected operations and notify board compliance committee',
    )
    esc2 = EscalationPath(
        name='Production Incident Authority',
        trigger_condition='P1/P2 incident requiring executive decision but CTO/VP Eng unavailable',
        domain_id=created_domains[6].id,
        step1_role_id=created_roles[1].id,  # VP Eng
        step2_role_id=created_roles[7].id,  # CTO
        step3_role_id=created_roles[0].id,  # COO
        ai_can_auto_escalate=True,
        max_wait_hours=1,
        fallback_action='On-call engineering lead authorized to make containment decisions with post-incident review',
    )
    esc3 = EscalationPath(
        name='Product Decision Continuity',
        trigger_condition='Product roadmap or prioritization decision stalled due to VP Product disruption',
        domain_id=created_domains[7].id,
        step1_role_id=created_roles[3].id,  # VP Product
        step2_role_id=created_roles[4].id,  # Dir AI Strategy (successor)
        step3_role_id=created_roles[0].id,  # COO
        ai_can_auto_escalate=False,
        max_wait_hours=48,
        fallback_action='COO convenes cross-functional product council for interim prioritization',
    )
    esc4 = EscalationPath(
        name='Budget Authority Escalation',
        trigger_condition='Budget decision >$100K requires CFO approval but CFO unavailable',
        domain_id=created_domains[0].id,
        step1_role_id=created_roles[5].id,  # CFO
        step2_role_id=created_roles[0].id,  # COO
        step3_role_id=None,
        ai_can_auto_escalate=False,
        max_wait_hours=24,
        fallback_action='Finance Director authorized for decisions up to $250K with post-approval review',
    )
    db.session.add_all([esc1, esc2, esc3, esc4])

    # ── Disruption Events ──
    e1 = DisruptionEvent(
        role_id=created_roles[3].id,
        event_type='medical',
        description='Extended medical leave — cardiac procedure recovery. 30-day anticipated absence.',
        interim_role_id=created_roles[4].id,
        affected_domains_count=1,
        status='active',
        started_at=datetime.utcnow() - timedelta(days=12),
    )
    e2 = DisruptionEvent(
        role_id=created_roles[7].id,
        event_type='exit',
        description='CTO departure — accepted external role. 30-day transition window.',
        interim_role_id=created_roles[1].id,
        affected_domains_count=2,
        status='active',
        started_at=datetime.utcnow() - timedelta(days=5),
    )
    db.session.add_all([e1, e2])

    # ── Governance Signals ──
    signals = [
        GovernanceSignal(
            signal_type='authority_gap', severity='critical',
            title='Authority gap: VP of Product disrupted — 1 domain affected',
            description='Marcus Weber unavailable (medical). Product Roadmap decisions stalled.',
            related_role_id=created_roles[3].id, status='active',
        ),
        GovernanceSignal(
            signal_type='decision_stall', severity='critical',
            title='Decision stall: Product Roadmap',
            description='Authority holder disrupted. Product Roadmap decisions may be paralyzed. Escalation path available.',
            related_role_id=created_roles[3].id, related_domain_id=created_domains[7].id, status='active',
        ),
        GovernanceSignal(
            signal_type='authority_gap', severity='warning',
            title='Authority transition: CTO role in 30-day handoff',
            description='Robert Tanaka departing. VP Engineering serving as interim. 2 domains in transition.',
            related_role_id=created_roles[7].id, status='active',
        ),
        GovernanceSignal(
            signal_type='overload', severity='warning',
            title='Role overload risk: VP of Engineering',
            description='James Chen now covering CTO duties in addition to VP Engineering. Cognitive load redistribution detected.',
            related_role_id=created_roles[1].id, status='active',
        ),
    ]
    db.session.add_all(signals)
    db.session.commit()


# ─── App Initialization ───────────────────────────────────────────────────────

with app.app_context():
    db.create_all()
    seed_demo_data()

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=os.environ.get('FLASK_DEBUG', 'false').lower() == 'true')
