import os
import json
from datetime import datetime, timedelta
from flask import Flask, render_template, request, redirect, url_for, flash, jsonify
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
from werkzeug.security import generate_password_hash, check_password_hash

app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'gov-continuity-dev-key-change-me')
app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get('DATABASE_URL', 'sqlite:///governance.db')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# Fix for postgres:// vs postgresql:// (Railway uses postgres://)
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
    role = db.Column(db.String(50), default='member')  # admin, member
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)


class Leader(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    title = db.Column(db.String(150), nullable=False)
    department = db.Column(db.String(100), nullable=False)
    status = db.Column(db.String(30), default='active')  # active, disrupted, transitioning
    disruption_type = db.Column(db.String(50), nullable=True)  # medical, burnout, exit, caregiving, other
    disruption_start = db.Column(db.DateTime, nullable=True)
    expected_return = db.Column(db.DateTime, nullable=True)
    successor_id = db.Column(db.Integer, db.ForeignKey('leader.id'), nullable=True)
    email = db.Column(db.String(120), nullable=True)
    notes = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    successor = db.relationship('Leader', remote_side=[id], backref='succeeds_for')


class DecisionDomain(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(150), nullable=False)
    description = db.Column(db.Text, nullable=True)
    category = db.Column(db.String(50), default='operational')  # strategic, operational, compliance, financial
    authority_leader_id = db.Column(db.Integer, db.ForeignKey('leader.id'), nullable=True)
    ai_support_level = db.Column(db.String(30), default='none')  # none, advisory, assisted, autonomous
    ai_boundary_notes = db.Column(db.Text, nullable=True)
    human_judgment_required = db.Column(db.Boolean, default=True)
    risk_level = db.Column(db.String(20), default='medium')  # low, medium, high, critical
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    authority_leader = db.relationship('Leader', backref='decision_domains')


class DisruptionEvent(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    leader_id = db.Column(db.Integer, db.ForeignKey('leader.id'), nullable=False)
    event_type = db.Column(db.String(50), nullable=False)
    description = db.Column(db.Text, nullable=True)
    started_at = db.Column(db.DateTime, default=datetime.utcnow)
    resolved_at = db.Column(db.DateTime, nullable=True)
    interim_leader_id = db.Column(db.Integer, db.ForeignKey('leader.id'), nullable=True)
    impact_assessment = db.Column(db.Text, nullable=True)
    actions_taken = db.Column(db.Text, nullable=True)
    status = db.Column(db.String(20), default='active')  # active, mitigated, resolved

    leader = db.relationship('Leader', foreign_keys=[leader_id], backref='disruption_events')
    interim_leader = db.relationship('Leader', foreign_keys=[interim_leader_id])


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
        flash('Account created successfully.', 'success')
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
    leaders = Leader.query.all()
    domains = DecisionDomain.query.all()
    active_disruptions = DisruptionEvent.query.filter_by(status='active').all()
    recent_logs = GovernanceLog.query.order_by(GovernanceLog.created_at.desc()).limit(10).all()

    stats = {
        'total_leaders': len(leaders),
        'active_leaders': sum(1 for l in leaders if l.status == 'active'),
        'disrupted_leaders': sum(1 for l in leaders if l.status == 'disrupted'),
        'total_domains': len(domains),
        'unassigned_domains': sum(1 for d in domains if not d.authority_leader_id),
        'ai_governed': sum(1 for d in domains if d.ai_support_level != 'none'),
        'critical_domains': sum(1 for d in domains if d.risk_level == 'critical'),
        'active_disruptions': len(active_disruptions),
    }

    # Governance health score
    if stats['total_leaders'] > 0:
        coverage = stats['active_leaders'] / stats['total_leaders']
    else:
        coverage = 1.0
    if stats['total_domains'] > 0:
        assigned = (stats['total_domains'] - stats['unassigned_domains']) / stats['total_domains']
    else:
        assigned = 1.0
    succession = sum(1 for l in leaders if l.successor_id) / max(len(leaders), 1)
    stats['health_score'] = int((coverage * 40 + assigned * 35 + succession * 25))

    return render_template('dashboard.html', stats=stats, leaders=leaders,
                           active_disruptions=active_disruptions, recent_logs=recent_logs)


# ─── Leaders ───────────────────────────────────────────────────────────────────

@app.route('/leaders')
@login_required
def leaders_list():
    leaders = Leader.query.order_by(Leader.department, Leader.name).all()
    return render_template('leaders.html', leaders=leaders)


@app.route('/leaders/add', methods=['GET', 'POST'])
@login_required
def add_leader():
    if request.method == 'POST':
        leader = Leader(
            name=request.form['name'],
            title=request.form['title'],
            department=request.form['department'],
            email=request.form.get('email', ''),
            status='active',
        )
        successor_id = request.form.get('successor_id')
        if successor_id:
            leader.successor_id = int(successor_id)
        db.session.add(leader)
        db.session.commit()
        log_action(f'Leader added: {leader.name} ({leader.title})')
        flash('Leader added.', 'success')
        return redirect(url_for('leaders_list'))
    all_leaders = Leader.query.order_by(Leader.name).all()
    return render_template('leader_form.html', leader=None, all_leaders=all_leaders)


@app.route('/leaders/<int:id>/edit', methods=['GET', 'POST'])
@login_required
def edit_leader(id):
    leader = Leader.query.get_or_404(id)
    if request.method == 'POST':
        leader.name = request.form['name']
        leader.title = request.form['title']
        leader.department = request.form['department']
        leader.email = request.form.get('email', '')
        leader.notes = request.form.get('notes', '')
        successor_id = request.form.get('successor_id')
        leader.successor_id = int(successor_id) if successor_id else None
        db.session.commit()
        log_action(f'Leader updated: {leader.name}')
        flash('Leader updated.', 'success')
        return redirect(url_for('leaders_list'))
    all_leaders = Leader.query.filter(Leader.id != id).order_by(Leader.name).all()
    return render_template('leader_form.html', leader=leader, all_leaders=all_leaders)


@app.route('/leaders/<int:id>/disrupt', methods=['GET', 'POST'])
@login_required
def disrupt_leader(id):
    leader = Leader.query.get_or_404(id)
    if request.method == 'POST':
        leader.status = 'disrupted'
        leader.disruption_type = request.form['disruption_type']
        leader.disruption_start = datetime.utcnow()
        exp_return = request.form.get('expected_return')
        if exp_return:
            leader.expected_return = datetime.strptime(exp_return, '%Y-%m-%d')

        event = DisruptionEvent(
            leader_id=leader.id,
            event_type=request.form['disruption_type'],
            description=request.form.get('description', ''),
            interim_leader_id=leader.successor_id,
            status='active',
        )
        db.session.add(event)
        db.session.commit()
        log_action(f'Disruption recorded: {leader.name} — {leader.disruption_type}')
        flash(f'Disruption recorded for {leader.name}.', 'warning')
        return redirect(url_for('leaders_list'))
    return render_template('disrupt_form.html', leader=leader)


@app.route('/leaders/<int:id>/restore', methods=['POST'])
@login_required
def restore_leader(id):
    leader = Leader.query.get_or_404(id)
    leader.status = 'active'
    leader.disruption_type = None
    leader.disruption_start = None
    leader.expected_return = None
    # Resolve active disruption events
    for event in leader.disruption_events:
        if event.status == 'active':
            event.status = 'resolved'
            event.resolved_at = datetime.utcnow()
    db.session.commit()
    log_action(f'Leader restored: {leader.name}')
    flash(f'{leader.name} has been restored to active status.', 'success')
    return redirect(url_for('leaders_list'))


@app.route('/leaders/<int:id>/delete', methods=['POST'])
@login_required
def delete_leader(id):
    leader = Leader.query.get_or_404(id)
    name = leader.name
    # Remove successor references
    for l in Leader.query.filter_by(successor_id=id).all():
        l.successor_id = None
    # Remove domain assignments
    for d in DecisionDomain.query.filter_by(authority_leader_id=id).all():
        d.authority_leader_id = None
    db.session.delete(leader)
    db.session.commit()
    log_action(f'Leader deleted: {name}')
    flash(f'{name} removed.', 'success')
    return redirect(url_for('leaders_list'))


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
        )
        leader_id = request.form.get('authority_leader_id')
        if leader_id:
            domain.authority_leader_id = int(leader_id)
        db.session.add(domain)
        db.session.commit()
        log_action(f'Decision domain added: {domain.name}')
        flash('Decision domain added.', 'success')
        return redirect(url_for('domains_list'))
    leaders = Leader.query.order_by(Leader.name).all()
    return render_template('domain_form.html', domain=None, leaders=leaders)


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
        leader_id = request.form.get('authority_leader_id')
        domain.authority_leader_id = int(leader_id) if leader_id else None
        db.session.commit()
        log_action(f'Decision domain updated: {domain.name}')
        flash('Domain updated.', 'success')
        return redirect(url_for('domains_list'))
    leaders = Leader.query.order_by(Leader.name).all()
    return render_template('domain_form.html', domain=domain, leaders=leaders)


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


# ─── Disruption Events / Timeline ─────────────────────────────────────────────

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
    log_action(f'Disruption event updated: {event.leader.name} — {event.status}')
    flash('Disruption event updated.', 'success')
    return redirect(url_for('disruptions_list'))


# ─── AI Governance Matrix ──────────────────────────────────────────────────────

@app.route('/ai-matrix')
@login_required
def ai_matrix():
    domains = DecisionDomain.query.order_by(DecisionDomain.risk_level.desc(), DecisionDomain.name).all()
    return render_template('ai_matrix.html', domains=domains)


# ─── Governance Audit Log ─────────────────────────────────────────────────────

@app.route('/audit-log')
@login_required
def audit_log():
    logs = GovernanceLog.query.order_by(GovernanceLog.created_at.desc()).limit(100).all()
    return render_template('audit_log.html', logs=logs)


# ─── API Endpoints for Dashboard Charts ────────────────────────────────────────

@app.route('/api/status-breakdown')
@login_required
def api_status_breakdown():
    leaders = Leader.query.all()
    breakdown = {}
    for l in leaders:
        breakdown[l.status] = breakdown.get(l.status, 0) + 1
    return jsonify(breakdown)


@app.route('/api/domain-risk')
@login_required
def api_domain_risk():
    domains = DecisionDomain.query.all()
    risk = {}
    for d in domains:
        risk[d.risk_level] = risk.get(d.risk_level, 0) + 1
    return jsonify(risk)


# ─── Helpers ───────────────────────────────────────────────────────────────────

def log_action(action, details=None, user_id=None):
    if user_id is None and current_user and current_user.is_authenticated:
        user_id = current_user.id
    entry = GovernanceLog(action=action, details=details, user_id=user_id)
    db.session.add(entry)
    db.session.commit()


def seed_demo_data():
    """Seed with demo data if database is empty."""
    if Leader.query.count() > 0:
        return

    # Leaders
    leaders_data = [
        ('Elena Vasquez', 'Chief Operating Officer', 'Operations', 'active'),
        ('James Chen', 'VP of Engineering', 'Engineering', 'active'),
        ('Sarah Okafor', 'Chief Compliance Officer', 'Legal & Compliance', 'active'),
        ('Marcus Weber', 'VP of Product', 'Product', 'disrupted'),
        ('Priya Sharma', 'Director of AI Strategy', 'Technology', 'active'),
        ('David Kim', 'CFO', 'Finance', 'active'),
        ('Aisha Johnson', 'Head of People Ops', 'Human Resources', 'active'),
        ('Robert Tanaka', 'CTO', 'Technology', 'transitioning'),
    ]

    created_leaders = []
    for name, title, dept, status in leaders_data:
        l = Leader(name=name, title=title, department=dept, status=status)
        if status == 'disrupted':
            l.disruption_type = 'medical'
            l.disruption_start = datetime.utcnow() - timedelta(days=12)
            l.expected_return = datetime.utcnow() + timedelta(days=18)
        elif status == 'transitioning':
            l.disruption_type = 'exit'
            l.disruption_start = datetime.utcnow() - timedelta(days=5)
        db.session.add(l)
        created_leaders.append(l)

    db.session.flush()

    # Set some successors
    created_leaders[3].successor_id = created_leaders[4].id  # Marcus -> Priya
    created_leaders[7].successor_id = created_leaders[1].id  # Robert -> James

    # Decision Domains
    domains_data = [
        ('Annual Budget Approval', 'Final approval of organizational budget', 'financial', 'critical', 5, 'advisory', True),
        ('AI Model Deployment', 'Approval to deploy AI models in production', 'compliance', 'critical', 4, 'assisted', True),
        ('Vendor Selection', 'Selection and approval of technology vendors', 'operational', 'high', 0, 'advisory', True),
        ('Sprint Planning', 'Engineering sprint priorities and allocation', 'operational', 'medium', 1, 'assisted', False),
        ('Data Privacy Compliance', 'GDPR/CCPA compliance decisions', 'compliance', 'critical', 2, 'advisory', True),
        ('Hiring Decisions', 'Final approval on new hires', 'operational', 'medium', 6, 'none', True),
        ('Incident Response', 'Production incident escalation decisions', 'operational', 'high', 0, 'assisted', True),
        ('Product Roadmap', 'Quarterly product direction decisions', 'strategic', 'high', 3, 'advisory', True),
        ('Customer Escalation', 'Executive-level customer issue resolution', 'operational', 'medium', 0, 'advisory', False),
        ('AI Ethics Review', 'Review of AI use cases for ethical alignment', 'compliance', 'critical', 4, 'none', True),
    ]

    for name, desc, cat, risk, leader_idx, ai_level, human_req in domains_data:
        d = DecisionDomain(
            name=name, description=desc, category=cat, risk_level=risk,
            ai_support_level=ai_level, human_judgment_required=human_req,
        )
        if leader_idx > 0:
            d.authority_leader_id = created_leaders[leader_idx].id
        db.session.add(d)

    # Disruption events
    e1 = DisruptionEvent(
        leader_id=created_leaders[3].id,
        event_type='medical',
        description='Extended medical leave — cardiac procedure recovery',
        interim_leader_id=created_leaders[4].id,
        status='active',
        started_at=datetime.utcnow() - timedelta(days=12),
    )
    e2 = DisruptionEvent(
        leader_id=created_leaders[7].id,
        event_type='exit',
        description='CTO departure — accepted role at another company. 30-day transition.',
        interim_leader_id=created_leaders[1].id,
        status='active',
        started_at=datetime.utcnow() - timedelta(days=5),
    )
    db.session.add(e1)
    db.session.add(e2)

    db.session.commit()


# ─── App Initialization ───────────────────────────────────────────────────────

with app.app_context():
    db.create_all()
    seed_demo_data()

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=os.environ.get('FLASK_DEBUG', 'false').lower() == 'true')
