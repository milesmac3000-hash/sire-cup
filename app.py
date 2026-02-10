from flask import Flask, render_template, request, redirect, url_for, jsonify, flash
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime
import json
from collections import defaultdict

import os

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'sire-cup-secret-key-2026')

# Use PostgreSQL on Render, SQLite locally
database_url = os.environ.get('DATABASE_URL', 'sqlite:///sirecup.db')
# Render uses postgres:// but SQLAlchemy needs postgresql://
if database_url.startswith('postgres://'):
    database_url = database_url.replace('postgres://', 'postgresql://', 1)
app.config['SQLALCHEMY_DATABASE_URI'] = database_url
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)

# Register datetime.utcnow as a global function for Jinja2 templates
app.jinja_env.globals.update(now=datetime.utcnow)

# Define Database Models
class Player(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(80), unique=True, nullable=False)
    handicap = db.Column(db.Float, nullable=False)
    team = db.Column(db.String(50), nullable=True)
    is_captain = db.Column(db.Boolean, default=False)
    travel_plans = db.relationship('TravelPlan', backref='player', lazy=True, cascade="all, delete-orphan")
    carpool_memberships = db.relationship('CarpoolMember', backref='player', lazy=True, cascade="all, delete-orphan")
    round_scores = db.relationship('PlayerRoundScore', backref='player', lazy=True, cascade="all, delete-orphan")
    paid_expenses = db.relationship('Expense', foreign_keys='[Expense.payer_id]', backref='payer', lazy=True)
    participating_expenses = db.relationship('ExpenseParticipant', backref='player', lazy=True, cascade="all, delete-orphan")

    def __repr__(self):
        return f'<Player {self.name}>'

class TravelPlan(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    player_id = db.Column(db.Integer, db.ForeignKey('player.id'), nullable=False)
    arrival_date = db.Column(db.DateTime, nullable=False)
    arrival_time = db.Column(db.String(50), nullable=True)
    airport_name = db.Column(db.String(100), nullable=True)
    flight_number = db.Column(db.String(50), nullable=True)
    departure_date = db.Column(db.DateTime, nullable=False)
    departure_time = db.Column(db.String(50), nullable=True)
    notes = db.Column(db.Text, nullable=True)

    def __repr__(self):
        return f'<TravelPlan {self.player.name} {self.arrival_date} to {self.departure_date}>'

class CarpoolGroup(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    description = db.Column(db.Text, nullable=True)
    max_members = db.Column(db.Integer, nullable=True)
    members = db.relationship('CarpoolMember', backref='carpool_group', lazy=True, cascade="all, delete-orphan")

    def __repr__(self):
        return f'<CarpoolGroup {self.name}>'

class CarpoolMember(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    carpool_id = db.Column(db.Integer, db.ForeignKey('carpool_group.id'), nullable=False)
    player_id = db.Column(db.Integer, db.ForeignKey('player.id'), nullable=False, unique=True)

    def __repr__(self):
        return f'<CarpoolMember {self.player.name} in {self.carpool_group.name}>'

class Course(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), unique=True, nullable=False)
    pars = db.Column(db.Text, nullable=False)
    rounds = db.relationship('Round', backref='course', lazy=True, cascade="all, delete-orphan")

    def get_pars_list(self):
        return json.loads(self.pars)

    def __repr__(self):
        return f'<Course {self.name}>'

class Round(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    course_id = db.Column(db.Integer, db.ForeignKey('course.id'), nullable=False)
    date = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    notes = db.Column(db.Text, nullable=True)
    team1_score = db.Column(db.Integer, nullable=True)
    team2_score = db.Column(db.Integer, nullable=True)
    scores = db.relationship('PlayerRoundScore', backref='round', lazy=True, cascade="all, delete-orphan")

    def __repr__(self):
        return f"<Round on {self.course.name} on {self.date.strftime('%Y-%m-%d')}>"

class PlayerRoundScore(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    round_id = db.Column(db.Integer, db.ForeignKey('round.id'), nullable=False)
    player_id = db.Column(db.Integer, db.ForeignKey('player.id'), nullable=False)
    hole_scores = db.Column(db.Text, nullable=False)
    total_score = db.Column(db.Integer, nullable=False)

    def get_hole_scores_list(self):
        return json.loads(self.hole_scores)

    def __repr__(self):
        return f'<PlayerRoundScore {self.player.name} Total: {self.total_score}>'

class Expense(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    description = db.Column(db.String(200), nullable=False)
    amount = db.Column(db.Float, nullable=False)
    payer_id = db.Column(db.Integer, db.ForeignKey('player.id'), nullable=False)
    date = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    notes = db.Column(db.Text, nullable=True)
    participants = db.relationship('ExpenseParticipant', backref='expense', lazy=True, cascade="all, delete-orphan")

    def __repr__(self):
        return f'<Expense {self.description} by {self.payer.name} for {self.amount}>'

class ExpenseParticipant(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    expense_id = db.Column(db.Integer, db.ForeignKey('expense.id'), nullable=False)
    player_id = db.Column(db.Integer, db.ForeignKey('player.id'), nullable=False)

    __table_args__ = (db.UniqueConstraint('expense_id', 'player_id', name='_expense_player_uc'),)

    def __repr__(self):
        return f'<Participant {self.player.name} in Expense {self.expense.description}>'

class Match(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    round_id = db.Column(db.Integer, db.ForeignKey('round.id'), nullable=True)
    date = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    format = db.Column(db.String(50), nullable=False)  # singles, fourball, foursomes, scramble
    status = db.Column(db.String(20), nullable=False, default='scheduled')  # scheduled, in_progress, completed
    
    # Team 1 players (JSON list of player IDs)
    team1_player_ids = db.Column(db.Text, nullable=False)
    # Team 2 players (JSON list of player IDs)
    team2_player_ids = db.Column(db.Text, nullable=False)
    
    # Results
    team1_points = db.Column(db.Float, nullable=True)  # 0, 0.5, or 1 (for ties/halves)
    team2_points = db.Column(db.Float, nullable=True)
    result_description = db.Column(db.String(100), nullable=True)  # e.g., "3&2", "1 up", "A/S"
    notes = db.Column(db.Text, nullable=True)

    def get_team1_players(self):
        return json.loads(self.team1_player_ids)
    
    def get_team2_players(self):
        return json.loads(self.team2_player_ids)

    def __repr__(self):
        return f'<Match {self.format} on {self.date}>'

class Announcement(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    content = db.Column(db.Text, nullable=False)
    author = db.Column(db.String(100), nullable=True)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    pinned = db.Column(db.Boolean, default=False)

    def __repr__(self):
        return f'<Announcement {self.title}>'

class ScheduleEvent(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text, nullable=True)
    event_date = db.Column(db.DateTime, nullable=False)
    start_time = db.Column(db.String(20), nullable=True)
    end_time = db.Column(db.String(20), nullable=True)
    location = db.Column(db.String(200), nullable=True)
    event_type = db.Column(db.String(50), nullable=False, default='general')  # golf, dinner, activity, travel, general
    course_id = db.Column(db.Integer, db.ForeignKey('course.id'), nullable=True)
    notes = db.Column(db.Text, nullable=True)

    def __repr__(self):
        return f'<ScheduleEvent {self.title} on {self.event_date}>'

class TripInfo(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False, default="Sire Cup 2026 - Annual Golf Extravaganza")
    dates = db.Column(db.String(100), nullable=False, default="October 23-27, 2026")
    location = db.Column(db.String(200), nullable=False, default="Pebble Beach, CA")
    message = db.Column(db.Text, nullable=False, default="Get ready for another epic Sire Cup! Handicaps are in, travel plans are shaping up, and the trash talk has already begun. Let's make some memories (and maybe a few birdies).")
    nav_links = db.Column(db.Text, nullable=False)
    team_names = db.Column(db.Text, nullable=False, default=json.dumps(["Team Augusta", "Team Magnolia"]))

    def get_nav_links_list(self):
        return json.loads(self.nav_links)

    def get_team_names_list(self):
        return json.loads(self.team_names)

    def __repr__(self):
        return f'<TripInfo {self.title}>'

# Create tables automatically on startup
with app.app_context():
    db.create_all()
    # Add departure_time column if it doesn't exist (migration)
    try:
        with db.engine.connect() as conn:
            conn.execute(db.text("ALTER TABLE travel_plan ADD COLUMN departure_time VARCHAR(50)"))
            conn.commit()
    except Exception:
        pass  # Column already exists

# Helper to get/create trip info
def get_or_create_trip_info():
    trip_info = TripInfo.query.first()
    if not trip_info:
        default_links = [
            {"text": "See All Players", "url": "/"},
            {"text": "View Travel Plans", "url": "/travel"},
            {"text": "Manage Carpools", "url": "/carpools"},
            {"text": "Manage Courses", "url": "/courses"},
            {"text": "Log & View Scores", "url": "/rounds"},
            {"text": "Manage Expenses", "url": "/expenses"},
            {"text": "Settle Up", "url": "/settle_up"},
        ]
        trip_info = TripInfo(nav_links=json.dumps(default_links))
        db.session.add(trip_info)
        db.session.commit()
    return trip_info


# Routes
@app.route('/')
def index():
    trip_info = get_or_create_trip_info()
    players = Player.query.all()
    courses = Course.query.all()
    rounds = Round.query.all()
    
    # Get match standings
    matches_list = Match.query.all()
    team1_points = sum(m.team1_points or 0 for m in matches_list if m.status == 'completed')
    team2_points = sum(m.team2_points or 0 for m in matches_list if m.status == 'completed')
    
    # Get recent announcements
    recent_announcements = Announcement.query.order_by(Announcement.pinned.desc(), Announcement.created_at.desc()).limit(3).all()
    
    return render_template('index.html', 
                          players=players, 
                          agenda=trip_info, 
                          courses=courses, 
                          rounds=rounds,
                          matches=matches_list,
                          team1_points=team1_points,
                          team2_points=team2_points,
                          announcements=recent_announcements)

@app.route('/edit_trip_info', methods=['GET', 'POST'])
def edit_trip_info():
    trip_info = get_or_create_trip_info()
    if request.method == 'POST':
        trip_info.title = request.form['title']
        trip_info.dates = request.form['dates']
        trip_info.location = request.form['location']
        trip_info.message = request.form['message']
        team_names_str = request.form['team_names']
        trip_info.team_names = json.dumps([name.strip() for name in team_names_str.split(',') if name.strip()])
        db.session.commit()
        return redirect(url_for('index'))
    return render_template('edit_trip_info.html', trip_info=trip_info)

@app.route('/add_player', methods=['GET', 'POST'])
def add_player():
    trip_info = get_or_create_trip_info()
    teams = trip_info.get_team_names_list()
    if request.method == 'POST':
        name = request.form['name']
        handicap = float(request.form['handicap'])
        team = request.form['team'] if request.form['team'] else None
        is_captain = bool(request.form.get('is_captain'))
        new_player = Player(name=name, handicap=handicap, team=team, is_captain=is_captain)
        db.session.add(new_player)
        db.session.commit()
        return redirect(url_for('index'))
    return render_template('add_player.html', teams=teams)

@app.route('/edit_player/<int:player_id>', methods=['GET', 'POST'])
def edit_player(player_id):
    player = Player.query.get_or_404(player_id)
    trip_info = get_or_create_trip_info()
    teams = trip_info.get_team_names_list()

    if request.method == 'POST':
        player.name = request.form['name']
        player.handicap = float(request.form['handicap'])
        player.team = request.form['team'] if request.form['team'] else None
        player.is_captain = bool(request.form.get('is_captain'))
        db.session.commit()
        return redirect(url_for('index'))
    
    return render_template('edit_player.html', player=player, teams=teams)

@app.route('/travel')
def travel():
    travel_plans = TravelPlan.query.order_by(TravelPlan.arrival_date, TravelPlan.arrival_time).all()
    players = Player.query.all()
    return render_template('travel.html', travel_plans=travel_plans, players=players)

@app.route('/add_travel_plan/<int:player_id>', methods=['GET', 'POST'])
def add_travel_plan(player_id):
    player = Player.query.get_or_404(player_id)
    if request.method == 'POST':
        arrival_str = request.form['arrival_date']
        arrival_time = request.form['arrival_time']
        airport_name = request.form['airport_name']
        flight_number = request.form['flight_number']
        departure_str = request.form['departure_date']
        departure_time = request.form.get('departure_time', '')
        notes = request.form['notes']

        arrival_date = datetime.strptime(arrival_str, '%Y-%m-%d')
        departure_date = datetime.strptime(departure_str, '%Y-%m-%d')

        new_plan = TravelPlan(
            player_id=player.id,
            arrival_date=arrival_date,
            arrival_time=arrival_time,
            airport_name=airport_name,
            flight_number=flight_number,
            departure_date=departure_date,
            departure_time=departure_time,
            notes=notes
        )
        db.session.add(new_plan)
        db.session.commit()
        return redirect(url_for('travel'))
    return render_template('add_travel_plan.html', player=player)

@app.route('/edit_travel_plan/<int:plan_id>', methods=['GET', 'POST'])
def edit_travel_plan(plan_id):
    plan = TravelPlan.query.get_or_404(plan_id)
    if request.method == 'POST':
        plan.arrival_date = datetime.strptime(request.form['arrival_date'], '%Y-%m-%d')
        plan.arrival_time = request.form['arrival_time']
        plan.airport_name = request.form['airport_name']
        plan.flight_number = request.form['flight_number']
        plan.departure_date = datetime.strptime(request.form['departure_date'], '%Y-%m-%d')
        plan.departure_time = request.form.get('departure_time', '')
        plan.notes = request.form['notes']
        db.session.commit()
        return redirect(url_for('travel'))
    return render_template('edit_travel_plan.html', plan=plan)

@app.route('/delete_travel_plan/<int:plan_id>')
def delete_travel_plan(plan_id):
    plan = TravelPlan.query.get_or_404(plan_id)
    db.session.delete(plan)
    db.session.commit()
    return redirect(url_for('travel'))

# --- Carpool Routes ---
@app.route('/carpools')
def carpools():
    carpool_groups = CarpoolGroup.query.all()
    players_not_in_carpool = Player.query.filter(~Player.carpool_memberships.any()).all()
    return render_template('carpools.html', carpool_groups=carpool_groups, players_not_in_carpool=players_not_in_carpool)

@app.route('/create_carpool', methods=['GET', 'POST'])
def create_carpool():
    if request.method == 'POST':
        name = request.form['name']
        description = request.form['description']
        max_members = request.form['max_members'] if request.form['max_members'] else None
        if max_members: max_members = int(max_members)
        new_carpool = CarpoolGroup(name=name, description=description, max_members=max_members)
        db.session.add(new_carpool)
        db.session.commit()
        return redirect(url_for('carpools'))
    return render_template('create_carpool.html')

@app.route('/join_carpool/<int:carpool_id>/<int:player_id>')
def join_carpool(carpool_id, player_id):
    existing_membership = CarpoolMember.query.filter_by(player_id=player_id).first()
    if existing_membership:
        db.session.delete(existing_membership)

    new_membership = CarpoolMember(carpool_id=carpool_id, player_id=player_id)
    db.session.add(new_membership)
    db.session.commit()
    return redirect(url_for('carpools'))

@app.route('/leave_carpool/<int:membership_id>')
def leave_carpool(membership_id):
    membership = CarpoolMember.query.get_or_404(membership_id)
    db.session.delete(membership)
    db.session.commit()
    return redirect(url_for('carpools'))

# --- Course & Round Routes ---
@app.route('/courses')
def courses():
    courses = Course.query.all()
    return render_template('courses.html', courses=courses)

@app.route('/add_course', methods=['GET', 'POST'])
def add_course():
    if request.method == 'POST':
        name = request.form['name']
        pars_str = request.form['pars']
        try:
            pars_list = [int(p.strip()) for p in pars_str.split(',') if p.strip()]
            if len(pars_list) != 18:
                raise ValueError("Please enter 18 pars, comma-separated.")
            pars_json = json.dumps(pars_list)
        except (ValueError, json.JSONDecodeError) as e:
            return render_template('add_course.html', error=str(e), name=name, pars=pars_str)

        new_course = Course(name=name, pars=pars_json)
        db.session.add(new_course)
        db.session.commit()
        return redirect(url_for('courses'))
    return render_template('add_course.html')

@app.route('/edit_course/<int:course_id>', methods=['GET', 'POST'])
def edit_course(course_id):
    course = Course.query.get_or_404(course_id)
    if request.method == 'POST':
        name = request.form['name']
        pars_str = request.form['pars']
        try:
            pars_list = [int(p.strip()) for p in pars_str.split(',') if p.strip()]
            if len(pars_list) != 18:
                raise ValueError("Please enter 18 pars, comma-separated.")
            course.name = name
            course.pars = json.dumps(pars_list)
            db.session.commit()
            return redirect(url_for('courses'))
        except (ValueError, json.JSONDecodeError) as e:
            return render_template('edit_course.html', course=course, error=str(e))
    return render_template('edit_course.html', course=course)

@app.route('/delete_course/<int:course_id>')
def delete_course(course_id):
    course = Course.query.get_or_404(course_id)
    db.session.delete(course)
    db.session.commit()
    return redirect(url_for('courses'))

@app.route('/rounds')
def rounds():
    rounds = Round.query.order_by(Round.date.desc()).all()
    courses = Course.query.all()
    players = Player.query.all()
    return render_template('rounds.html', rounds=rounds, courses=courses, players=players)

@app.route('/log_round/<int:course_id>', methods=['GET', 'POST'])
def log_round(course_id):
    course = Course.query.get_or_404(course_id)
    players = Player.query.all()

    if request.method == 'POST':
        round_notes = request.form.get('round_notes')
        new_round = Round(course_id=course.id, notes=round_notes)
        db.session.add(new_round)
        db.session.flush()

        for player in players:
            hole_scores = []
            total_score = 0
            player_scores_entered = False
            for i in range(1, 19):
                score_key = f'player_{player.id}_hole_{i}'
                score_val = request.form.get(score_key)
                if score_val is not None and score_val.strip() != '':
                    score = int(score_val)
                    player_scores_entered = True
                else:
                    score = course.get_pars_list()[i-1]
                hole_scores.append(score)
                total_score += score
            
            if player_scores_entered:
                new_player_score = PlayerRoundScore(
                    round_id=new_round.id,
                    player_id=player.id,
                    hole_scores=json.dumps(hole_scores),
                    total_score=total_score
                )
                db.session.add(new_player_score)
        
        db.session.commit()
        return redirect(url_for('rounds'))

    return render_template('log_round.html', course=course, players=players, course_pars=course.get_pars_list())

@app.route('/view_round_scores/<int:round_id>')
def view_round_scores(round_id):
    round_data = Round.query.get_or_404(round_id)
    player_scores = PlayerRoundScore.query.filter_by(round_id=round_id).all()
    return render_template('view_round_scores.html', round_data=round_data, player_scores=player_scores)

# --- Expense Routes ---
@app.route('/expenses')
def expenses():
    expenses_list = Expense.query.order_by(Expense.date.desc()).all()
    return render_template('expenses.html', expenses_list=expenses_list)

@app.route('/add_expense', methods=['GET', 'POST'])
def add_expense():
    players = Player.query.all()
    if request.method == 'POST':
        description = request.form['description']
        amount = float(request.form['amount'])
        payer_id = int(request.form['payer_id'])
        notes = request.form.get('notes')
        participant_ids = request.form.getlist('participants')

        new_expense = Expense(description=description, amount=amount, payer_id=payer_id, notes=notes)
        db.session.add(new_expense)
        db.session.flush()

        for pid in participant_ids:
            participant = ExpenseParticipant(expense_id=new_expense.id, player_id=int(pid))
            db.session.add(participant)
        
        db.session.commit()
        return redirect(url_for('expenses'))
    return render_template('add_expense.html', players=players)

@app.route('/edit_expense/<int:expense_id>', methods=['GET', 'POST'])
def edit_expense(expense_id):
    expense = Expense.query.get_or_404(expense_id)
    players = Player.query.all()
    if request.method == 'POST':
        expense.description = request.form['description']
        expense.amount = float(request.form['amount'])
        expense.payer_id = int(request.form['payer_id'])
        expense.notes = request.form.get('notes')
        
        # Update participants
        ExpenseParticipant.query.filter_by(expense_id=expense.id).delete()
        participant_ids = request.form.getlist('participants')
        for pid in participant_ids:
            participant = ExpenseParticipant(expense_id=expense.id, player_id=int(pid))
            db.session.add(participant)
        
        db.session.commit()
        return redirect(url_for('expenses'))
    
    current_participant_ids = [p.player_id for p in expense.participants]
    return render_template('edit_expense.html', expense=expense, players=players, current_participant_ids=current_participant_ids)

@app.route('/delete_expense/<int:expense_id>')
def delete_expense(expense_id):
    expense = Expense.query.get_or_404(expense_id)
    db.session.delete(expense)
    db.session.commit()
    return redirect(url_for('expenses'))

@app.route('/delete_player/<int:player_id>')
def delete_player(player_id):
    player = Player.query.get_or_404(player_id)
    db.session.delete(player)
    db.session.commit()
    return redirect(url_for('index'))

@app.route('/settle_up')
def settle_up():
    players = Player.query.all()
    expenses = Expense.query.all()

    balances = defaultdict(float)
    for player in players:
        balances[player.id] = 0.0
    
    for expense in expenses:
        payer = expense.payer
        balances[payer.id] += expense.amount

        if expense.participants:
            share_per_person = expense.amount / len(expense.participants)
            for participant in expense.participants:
                balances[participant.player.id] -= share_per_person

    debtors = []
    creditors = []
    for player in players:
        if balances[player.id] < 0:
            debtors.append({'player': player, 'amount': abs(balances[player.id])})
        elif balances[player.id] > 0:
            creditors.append({'player': player, 'amount': balances[player.id]})
    
    transactions = []
    debtors.sort(key=lambda x: x['amount'], reverse=True)
    creditors.sort(key=lambda x: x['amount'], reverse=True)

    i, j = 0, 0
    while i < len(debtors) and j < len(creditors):
        debtor = debtors[i]
        creditor = creditors[j]

        amount_to_settle = min(debtor['amount'], creditor['amount'])
        if amount_to_settle > 0.01:
            transactions.append({
                'from': debtor['player'].name,
                'to': creditor['player'].name,
                'amount': round(amount_to_settle, 2)
            })

            debtor['amount'] -= amount_to_settle
            creditor['amount'] -= amount_to_settle

        if debtor['amount'] < 0.01:
            i += 1
        if creditor['amount'] < 0.01:
            j += 1

    return render_template('settle_up.html', players=players, expenses=expenses, balances=balances, transactions=transactions)


# --- Match/Competition Routes ---
@app.route('/matches')
def matches():
    matches_list = Match.query.order_by(Match.date.desc()).all()
    players = Player.query.all()
    players_dict = {p.id: p for p in players}
    trip_info = get_or_create_trip_info()
    team_names = trip_info.get_team_names_list()
    
    # Calculate team standings
    team1_points = sum(m.team1_points or 0 for m in matches_list if m.status == 'completed')
    team2_points = sum(m.team2_points or 0 for m in matches_list if m.status == 'completed')
    
    return render_template('matches.html', 
                          matches=matches_list, 
                          players=players,
                          players_dict=players_dict,
                          team_names=team_names,
                          team1_points=team1_points,
                          team2_points=team2_points)

@app.route('/create_match', methods=['GET', 'POST'])
def create_match():
    trip_info = get_or_create_trip_info()
    team_names = trip_info.get_team_names_list()
    players = Player.query.all()
    
    # Split players by team
    team1_players = [p for p in players if p.team == team_names[0]] if len(team_names) > 0 else []
    team2_players = [p for p in players if p.team == team_names[1]] if len(team_names) > 1 else []
    
    if request.method == 'POST':
        format_type = request.form['format']
        match_date = datetime.strptime(request.form['date'], '%Y-%m-%d')
        team1_ids = request.form.getlist('team1_players')
        team2_ids = request.form.getlist('team2_players')
        notes = request.form.get('notes', '')
        
        new_match = Match(
            format=format_type,
            date=match_date,
            team1_player_ids=json.dumps([int(id) for id in team1_ids]),
            team2_player_ids=json.dumps([int(id) for id in team2_ids]),
            notes=notes,
            status='scheduled'
        )
        db.session.add(new_match)
        db.session.commit()
        return redirect(url_for('matches'))
    
    return render_template('create_match.html', 
                          team_names=team_names,
                          team1_players=team1_players,
                          team2_players=team2_players)

@app.route('/edit_match/<int:match_id>', methods=['GET', 'POST'])
def edit_match(match_id):
    match = Match.query.get_or_404(match_id)
    trip_info = get_or_create_trip_info()
    team_names = trip_info.get_team_names_list()
    players = Player.query.all()
    
    team1_players = [p for p in players if p.team == team_names[0]] if len(team_names) > 0 else []
    team2_players = [p for p in players if p.team == team_names[1]] if len(team_names) > 1 else []
    
    if request.method == 'POST':
        match.format = request.form['format']
        match.date = datetime.strptime(request.form['date'], '%Y-%m-%d')
        match.team1_player_ids = json.dumps([int(id) for id in request.form.getlist('team1_players')])
        match.team2_player_ids = json.dumps([int(id) for id in request.form.getlist('team2_players')])
        match.status = request.form['status']
        match.notes = request.form.get('notes', '')
        
        # Handle results if completed
        if match.status == 'completed':
            result = request.form.get('result')
            match.result_description = request.form.get('result_description', '')
            if result == 'team1':
                match.team1_points = 1.0
                match.team2_points = 0.0
            elif result == 'team2':
                match.team1_points = 0.0
                match.team2_points = 1.0
            elif result == 'halved':
                match.team1_points = 0.5
                match.team2_points = 0.5
        
        db.session.commit()
        return redirect(url_for('matches'))
    
    return render_template('edit_match.html', 
                          match=match,
                          team_names=team_names,
                          team1_players=team1_players,
                          team2_players=team2_players,
                          current_team1_ids=match.get_team1_players(),
                          current_team2_ids=match.get_team2_players())

@app.route('/delete_match/<int:match_id>')
def delete_match(match_id):
    match = Match.query.get_or_404(match_id)
    db.session.delete(match)
    db.session.commit()
    return redirect(url_for('matches'))


# --- Announcement Routes ---
@app.route('/announcements')
def announcements():
    announcements_list = Announcement.query.order_by(Announcement.pinned.desc(), Announcement.created_at.desc()).all()
    return render_template('announcements.html', announcements=announcements_list)

@app.route('/create_announcement', methods=['GET', 'POST'])
def create_announcement():
    if request.method == 'POST':
        title = request.form['title']
        content = request.form['content']
        author = request.form.get('author', '')
        pinned = bool(request.form.get('pinned'))
        
        new_announcement = Announcement(title=title, content=content, author=author, pinned=pinned)
        db.session.add(new_announcement)
        db.session.commit()
        return redirect(url_for('announcements'))
    
    return render_template('create_announcement.html')

@app.route('/edit_announcement/<int:announcement_id>', methods=['GET', 'POST'])
def edit_announcement(announcement_id):
    announcement = Announcement.query.get_or_404(announcement_id)
    if request.method == 'POST':
        announcement.title = request.form['title']
        announcement.content = request.form['content']
        announcement.author = request.form.get('author', '')
        announcement.pinned = bool(request.form.get('pinned'))
        db.session.commit()
        return redirect(url_for('announcements'))
    return render_template('edit_announcement.html', announcement=announcement)

@app.route('/delete_announcement/<int:announcement_id>')
def delete_announcement(announcement_id):
    announcement = Announcement.query.get_or_404(announcement_id)
    db.session.delete(announcement)
    db.session.commit()
    flash('Announcement deleted', 'success')
    return redirect(url_for('announcements'))


# --- Schedule Routes ---
@app.route('/schedule')
def schedule():
    events = ScheduleEvent.query.order_by(ScheduleEvent.event_date, ScheduleEvent.start_time).all()
    courses = Course.query.all()
    
    # Group events by date
    events_by_date = {}
    for event in events:
        date_key = event.event_date.strftime('%Y-%m-%d')
        if date_key not in events_by_date:
            events_by_date[date_key] = []
        events_by_date[date_key].append(event)
    
    return render_template('schedule.html', events=events, events_by_date=events_by_date, courses=courses)

@app.route('/create_event', methods=['GET', 'POST'])
def create_event():
    courses = Course.query.all()
    if request.method == 'POST':
        title = request.form['title']
        description = request.form.get('description', '')
        event_date = datetime.strptime(request.form['event_date'], '%Y-%m-%d')
        start_time = request.form.get('start_time', '')
        end_time = request.form.get('end_time', '')
        location = request.form.get('location', '')
        event_type = request.form['event_type']
        course_id = request.form.get('course_id') if request.form.get('course_id') else None
        notes = request.form.get('notes', '')
        
        new_event = ScheduleEvent(
            title=title,
            description=description,
            event_date=event_date,
            start_time=start_time,
            end_time=end_time,
            location=location,
            event_type=event_type,
            course_id=int(course_id) if course_id else None,
            notes=notes
        )
        db.session.add(new_event)
        db.session.commit()
        flash('Event added to schedule!', 'success')
        return redirect(url_for('schedule'))
    
    return render_template('create_event.html', courses=courses)

@app.route('/edit_event/<int:event_id>', methods=['GET', 'POST'])
def edit_event(event_id):
    event = ScheduleEvent.query.get_or_404(event_id)
    courses = Course.query.all()
    
    if request.method == 'POST':
        event.title = request.form['title']
        event.description = request.form.get('description', '')
        event.event_date = datetime.strptime(request.form['event_date'], '%Y-%m-%d')
        event.start_time = request.form.get('start_time', '')
        event.end_time = request.form.get('end_time', '')
        event.location = request.form.get('location', '')
        event.event_type = request.form['event_type']
        event.course_id = int(request.form.get('course_id')) if request.form.get('course_id') else None
        event.notes = request.form.get('notes', '')
        db.session.commit()
        flash('Event updated!', 'success')
        return redirect(url_for('schedule'))
    
    return render_template('edit_event.html', event=event, courses=courses)

@app.route('/delete_event/<int:event_id>')
def delete_event(event_id):
    event = ScheduleEvent.query.get_or_404(event_id)
    db.session.delete(event)
    db.session.commit()
    flash('Event deleted', 'success')
    return redirect(url_for('schedule'))


# --- API endpoint for standings ---
@app.route('/api/standings')
def api_standings():
    matches_list = Match.query.filter_by(status='completed').all()
    trip_info = get_or_create_trip_info()
    team_names = trip_info.get_team_names_list()
    
    team1_points = sum(m.team1_points or 0 for m in matches_list)
    team2_points = sum(m.team2_points or 0 for m in matches_list)
    
    return jsonify({
        'team1': {'name': team_names[0] if len(team_names) > 0 else 'Team 1', 'points': team1_points},
        'team2': {'name': team_names[1] if len(team_names) > 1 else 'Team 2', 'points': team2_points},
        'matches_played': len(matches_list)
    })


if __name__ == '__main__':
    with app.app_context():
        db.create_all()
    app.run(debug=True)
