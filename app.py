from flask import Flask, jsonify, request
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import Column, String, JSON, Float
from flask_migrate import Migrate
from flask_swagger_ui import get_swaggerui_blueprint
import yaml
import json
import hashlib
import time
import random
import string
import os

app = Flask(__name__)
# app.config['SQLALCHEMY_DATABASE_URI'] = 'postgresql://kshitij:kshitij@localhost:5432/merchant_sr'
app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get("RENDER_DATABASE_URL")
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)
migrate = Migrate(app, db)

with open('static/swagger.yaml', 'r') as f:
    swagger_data = yaml.safe_load(f)

SWAGGER_URL = '/api/docs'
API_URL = '/static/swagger.yaml'

swaggerui_blueprint = get_swaggerui_blueprint(
    SWAGGER_URL,
    API_URL,
    config={  
        'app_name': "Merchant SR Booster"
    }
)
app.register_blueprint(swaggerui_blueprint, url_prefix=SWAGGER_URL)


# Utility function to generate a 6-character unique hash
def generate_unique_hash(prefix):
    return f"{prefix}_{''.join(random.choices(string.ascii_lowercase + string.digits, k=6))}"

# Model Definitions
class Feature(db.Model):
    __tablename__ = 'features'
    
    feature_id = Column(String(50), primary_key=True)
    method = Column(String(50))
    category_types = Column(JSON)  # Store as JSON to support arrays
    checkout_types = Column(JSON)   # Store as JSON to support arrays
    feature_name = Column(String(100))
    feature_flag = Column(String(50))
    description = Column(String(255))

class Merchant(db.Model):
    __tablename__ = 'merchants'
    
    mid = Column(String(10), primary_key=True)  # Keeping this 10 chars long
    merchant_name = Column(String(100))
    mx_category_type = Column(String(50))
    mx_checkout_type = Column(String(50))
    mx_methods = Column(JSON)  # Change to JSON to support multiple methods
    gmv = Column(Float)
    tier = Column(String(50))
    current_overall_sr = Column(Float)
    predicted_overall_sr = Column(Float)
    current_method_specific_sr = Column(JSON)
    predicted_method_specific_sr = Column(JSON)

class Request(db.Model):
    __tablename__ = 'requests'
    request_id = db.Column(db.String, primary_key=True)
    mid = db.Column(db.String, db.ForeignKey('merchants.mid'))
    feature_id = db.Column(db.String, db.ForeignKey('features.feature_id'))
    method = db.Column(db.String)
    feature_name = db.Column(db.String)
    feature_flag = db.Column(db.String)
    status = db.Column(db.String)
    created_at = db.Column(db.Integer)  # Unix timestamp
    updated_at = db.Column(db.Integer)  # Unix timestamp
    pricing_config = db.Column(db.Text)

# API Endpoints
@app.route('/features', methods=['GET'])
def get_features():
    features = Feature.query.all()
    features_data = [{
        'feature_id': f.feature_id,
        'feature_name': f.feature_name,
        'method': f.method,
        'description': f.description,
        'category_types': f.category_types,  # No need for json.loads here
        'checkout_types': f.checkout_types   # No need for json.loads here
    } for f in features]
    
    return jsonify(features_data), 200

@app.route('/features/<feature_id>', methods=['GET'])
def get_feature(feature_id):
    feature = Feature.query.filter_by(feature_id=feature_id).first()
    if not feature:
        return jsonify({'error': 'Feature not found'}), 404
    
    return jsonify({
        'feature_id': feature.feature_id,
        'method': feature.method,
        'category_types': feature.category_types,  # No need for json.loads
        'checkout_types': feature.checkout_types,  # No need for json.loads
        'feature_name': feature.feature_name,
        'feature_flag': feature.feature_flag,
        'description': feature.description
    })

@app.route('/merchants/<mid>', methods=['GET'])
def get_merchant(mid):
    merchant = Merchant.query.filter_by(mid=mid).first()
    if not merchant:
        return jsonify({'error': 'Merchant not found'}), 404
    
    return jsonify({
        'mid': merchant.mid,
        'merchant_name': merchant.merchant_name,
        'mx_category_type': merchant.mx_category_type,
        'mx_checkout_type': merchant.mx_checkout_type,
        'mx_methods': merchant.mx_methods,  # No need for json.loads
        'gmv': merchant.gmv,
        'tier': merchant.tier,
        'current_overall_sr': merchant.current_overall_sr,
        'predicted_overall_sr': merchant.predicted_overall_sr,
        'current_method_specific_sr': merchant.current_method_specific_sr,  # No need for json.loads
        'predicted_method_specific_sr': merchant.predicted_method_specific_sr  # No need for json.loads
    }), 200

@app.route('/merchants/<string:mid>/features', methods=['GET'])
def get_merchant_features(mid):
    merchant = Merchant.query.get(mid)
    if not merchant:
        return jsonify({'error': 'Merchant not found'}), 404

    relevant_features = Feature.query.filter(
        Feature.method.in_(merchant.mx_methods),
        Feature.category_types.contains(merchant.mx_category_type),
        Feature.checkout_types.contains(merchant.mx_checkout_type)
    ).all()
    
    methods_features_data = {}
    for feature in relevant_features:
        if feature.method not in methods_features_data:
            methods_features_data[feature.method] = []
        methods_features_data[feature.method].append({
            'feature_id': feature.feature_id,
            'feature_name': feature.feature_name,
            'feature_flag': feature.feature_flag,
            'description': feature.description,
            'category_types': feature.category_types,  # No need for json.loads
            'checkout_types': feature.checkout_types   # No need for json.loads
        })
    
    return jsonify(methods_features_data), 200

@app.route('/merchants/<string:mid>/sr-booster', methods=['GET'])
def get_sr_booster(mid):
    merchant = Merchant.query.get(mid)
    if not merchant:
        return jsonify({'error': 'Merchant not found'}), 404
    
    return jsonify({
        'merchant': {
            'merchant_name': merchant.merchant_name,
            'current_overall_sr': merchant.current_overall_sr,
            'predicted_overall_sr': merchant.predicted_overall_sr,
            'current_method_specific_sr': merchant.current_method_specific_sr,  # No need for json.loads
            'predicted_method_specific_sr': merchant.predicted_method_specific_sr  # No need for json.loads
        }
    }), 200

@app.route('/requests', methods=['POST'])
def create_request():
    data = request.json
    if not all(k in data for k in ('feature_id', 'mid')):
        return jsonify({'error': 'Missing required fields: feature_id, mid'}), 400
    
    feature_id = data['feature_id']
    mid = data['mid']
    
    # Ensure merchant and feature exist
    merchant = Merchant.query.get(mid)
    feature = Feature.query.get(feature_id)
    if not merchant or not feature:
        return jsonify({'error': 'Merchant or Feature not found'}), 404
    
    # Generate request ID
    request_id = generate_unique_hash("req")
    
    new_request = Request(
        request_id=request_id,
        mid=merchant.mid,
        feature_id=feature.feature_id,
        method=feature.method,
        feature_name=feature.feature_name,
        feature_flag=feature.feature_flag,
        status='pending',
        created_at=int(time.time()),
        updated_at=int(time.time()),
        pricing_config=json.dumps(data.get('pricing_config', {}))
    )

    db.session.add(new_request)
    db.session.commit()

    return jsonify({'message': 'Request created', 'request_id': new_request.request_id}), 201

@app.route('/requests', methods=['GET'])
def get_requests():
    requests = Request.query.all()
    requests_data = [{
        'request_id': r.request_id,
        'mid': r.mid,
        'feature_id': r.feature_id,
        'method': r.method,
        'feature_name': r.feature_name,
        'feature_flag': r.feature_flag,
        'status': r.status,
        'created_at': r.created_at,
        'updated_at': r.updated_at
    } for r in requests]
    
    return jsonify(requests_data), 200

@app.route('/requests/<string:request_id>', methods=['GET'])
def get_request_by_id(request_id):
    request_entry = Request.query.get(request_id)
    if not request_entry:
        return jsonify({'error': 'Request not found'}), 404

    request_data = {
        'request_id': request_entry.request_id,
        'mid': request_entry.mid,
        'feature_id': request_entry.feature_id,
        'method': request_entry.method,
        'feature_name': request_entry.feature_name,
        'feature_flag': request_entry.feature_flag,
        'status': request_entry.status,
        'created_at': request_entry.created_at,
        'updated_at': request_entry.updated_at,
        'pricing_config': json.loads(request_entry.pricing_config) if request_entry.pricing_config else {}  # Keep this as it might not be JSON in the DB
    }

    return jsonify(request_data), 200

@app.route('/admin/pending-approvals', methods=['GET'])
def get_pending_approvals():
    pending_requests = Request.query.filter_by(status='pending').all()
    requests_data = [{
        'request_id': r.request_id,
        'mid': r.mid,
        'feature_id': r.feature_id,
        'feature_name': r.feature_name,
        'status': r.status,
        'created_at': r.created_at
    } for r in pending_requests]
    
    return jsonify({'pending_requests': requests_data}), 200  # Consistent response format

@app.route('/admin/requests/<string:request_id>/approve', methods=['PATCH'])  # Changed to PATCH
def approve_request(request_id):
    request_entry = Request.query.get(request_id)
    if not request_entry:
        return jsonify({'error': 'Request not found'}), 404
    
    if request_entry.status != 'pending':
        return jsonify({'error': 'Request cannot be approved; it is not pending'}), 400

    request_entry.status = 'approved'
    request_entry.updated_at = int(time.time())
    db.session.commit()

    return jsonify({
        'message': 'Request approved',
        'request_id': request_entry.request_id,
        'status': request_entry.status,
        'updated_at': request_entry.updated_at
    }), 200

@app.route('/admin/requests/<string:request_id>/reject', methods=['PATCH'])  # Changed to PATCH
def reject_request(request_id):
    request_entry = Request.query.get(request_id)
    if not request_entry:
        return jsonify({'error': 'Request not found'}), 404
    
    if request_entry.status != 'pending':
        return jsonify({'error': 'Request cannot be rejected; it is not pending'}), 400

    request_entry.status = 'rejected'
    request_entry.updated_at = int(time.time())
    db.session.commit()

    return jsonify({
        'message': 'Request rejected',
        'request_id': request_entry.request_id,
        'status': request_entry.status,
        'updated_at': request_entry.updated_at
    }), 200

if __name__ == '__main__':
    app.run(debug=True, port=5501)